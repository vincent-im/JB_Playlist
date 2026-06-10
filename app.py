import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
from streamlit_sortables import sort_items
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import googleapiclient.errors

# ------------------------------------------------------------------
# 1. 초기 세션 상태 및 기본 설정
# ------------------------------------------------------------------
st.set_page_config(page_title="중앙성가 플레이리스트 자동화 에이전트", layout="wide")
st.title("🎼 중앙성가 맞춤형 유튜브 플레이리스트 자동화 에이전트")
st.caption("유튜브 ID: vincent.jbim@gmail.com")

if "playlist_items" not in st.session_state:
    st.session_state.playlist_items = []

if "songbooks" not in st.session_state:
    st.session_state.songbooks = {}

if "extracted_buffer" not in st.session_state:
    st.session_state.extracted_buffer = {}

PART_MAPPING = {
    "합창": "Test(합창)",
    "소프": "Test(S)",
    "알토": "Test(A)",
    "테너": "Test(T)",
    "베이스": "Test(B)",
    "반주": "Test(반주)"
}

# ------------------------------------------------------------------
# 2. 🔍 [🚨 풀다운 먹통 버그 원천 해결] 중앙성가 정밀 빌더 엔진
# ------------------------------------------------------------------
def extract_songs_from_joongang(songbook_url):
    """
    중앙성가 메인 페이지에서 '번호. 곡명' 구조를 100% 확률로 안전하게 파싱합니다.
    a 태그뿐만 아니라 td 내부 텍스트까지 순회하여 풀다운 메뉴가 누락되지 않도록 방어합니다.
    """
    songs_db = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(songbook_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 주소 베이스 경로 정제 (예: https://joongangart.kr/joongang48/)
        # .html로 끝나는 파일명이 있으면 잘라내고 폴더 주소만 남깁니다.
        base_dir = songbook_url.rsplit('/', 1)[0] + '/'
        if '.html' in base_dir:
            base_dir = base_dir.rsplit('/', 1)[0] + '/'
            
        # [방어 메커니즘] 페이지 내부의 모든 엘리먼트를 돌며 '숫자. 곡제목' 패턴 스캔
        for element in soup.find_all(['a', 'td', 'font', 'span']):
            text = element.get_text().strip()
            
            # "01. 나의 힘이 되신 주님", "31. 축도송" 형태 정밀 추적 (줄바꿈 노이즈 제거)
            text_clean = re.sub(r'\s+', ' ', text)
            match = re.search(r'^(\d+)\.\s*([^\d]+.*)$', text_clean)
            
            if match:
                song_num = match.group(1).zfill(2) # "01", "02" 형태로 두 자리 고정
                song_title = match.group(2).strip()
                full_display_name = f"{song_num}. {song_title}"
                
                # 💡 중복 주소 버그 해결: 무조건 최상위 폴더 경로 밑에 '곡번호/pop1.html'로 고정 조립
                # 결과: https://joongangart.kr/joongang48/01/pop1.html
                constructed_sub_url = f"{base_dir}{song_num}/pop1.html"
                songs_db[full_display_name] = constructed_sub_url
                    
        return songs_db
    except Exception as e:
        st.error(f"❌ 악보집 파싱 중 치명적 오류 발생: {e}")
        return None

def extract_video_id_powerful(text_content):
    """ 소스코드 내부에서 11자리 유튜브 ID 패턴을 탐지합니다. """
    patterns = [
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'v=([a-zA-Z0-9_-]{11})',
        r'/[vV]/([a-zA-Z0-9_-]{11})',
        r'["\']([a-zA-Z0-9_-]{11})["\']'
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text_content)
        for vid in matches:
            if len(vid) == 11 and not any(k in vid.lower() for k in ['http', 'html', 'href', 'scro', 'name', 'col_', 'text', 'java']):
                return vid
    return None

def deep_extract_youtube_urls(main_html_url):
    """ pop1.html 페이지 내에 배치된 6개 파트용 하위 페이지 주소를 정밀 수집합니다. """
    final_result = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(main_html_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
            
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a')
        sub_page_urls = {}
        
        # 1단계: 텍스트 기반 매칭 (합창, 소프, 알토 등)
        for part_key in PART_MAPPING.keys():
            for link in links:
                link_text = link.get_text().strip()
                link_href = link.get('href', '')
                if part_key in link_text or part_key in link_href:
                    sub_page_urls[part_key] = urljoin(main_html_url, link_href)
                    break
                    
        # 2단계: 순서 기반 배열 매칭 백업
        if len(sub_page_urls) < 6:
            valid_hrefs = [urljoin(main_html_url, l.get('href')) for l in links if l.get('href') and not l.get('href').startswith('#')]
            valid_hrefs = [u for u in list(dict.fromkeys(valid_hrefs)) if u != main_html_url]
            for i, part_key in enumerate(PART_MAPPING.keys()):
                if i < len(valid_hrefs) and part_key not in sub_page_urls:
                    sub_page_urls[part_key] = valid_hrefs[i]

        # 3단계: 파트별 최종 페이지 접속 후 진짜 유튜브 비디오 ID 추출
        for part_key, playlist_name in PART_MAPPING.items():
            target_sub_url = sub_page_urls.get(part_key)
            if target_sub_url:
                try:
                    sub_res = requests.get(target_sub_url, headers=headers, timeout=5)
                    sub_res.encoding = sub_res.apparent_encoding
                    video_id = extract_video_id_powerful(sub_res.text)
                    if video_id:
                        final_result[playlist_name] = f"https://www.youtube.com/watch?v={video_id}"
                    else:
                        final_result[playlist_name] = ""
                except:
                    final_result[playlist_name] = ""
            else:
                final_result[playlist_name] = ""
        return final_result
    except:
        return None

# ------------------------------------------------------------------
# 3. 구글 공식 YouTube Data API v3 연동 백엔드 모듈
# ------------------------------------------------------------------
def get_youtube_service():
    try:
        creds = Credentials(
            token=None, refresh_token=st.secrets["google"]["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=st.secrets["google"]["client_id"], client_secret=st.secrets["google"]["client_secret"]
        )
        return build('youtube', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"❌ 구글 인증 세션 로드 에러: {e}")
        return None

def get_or_create_playlist(youtube, title):
    try:
        request = youtube.playlists().list(part="snippet", mine=True, maxResults=50)
        response = request.execute()
        for item in response.get("items", []):
            if item["snippet"]["title"] == title: 
                return item["id"]
        
        create_request = youtube.playlists().insert(
            part="snippet,status", 
            body={"snippet": {"title": title, "description": "에이전트 자동화 생성"}, "status": {"privacyStatus": "private"}}
        )
        return create_request.execute()["id"]
    except Exception as e:
        st.error(f"❌ 플레이리스트 핸들링 오류: {e}")
        return None

def add_video_to_playlist(youtube, p_id, v_id):
    try:
        request = youtube.playlistItems().insert(
            part="snippet", 
            body={"snippet": {"playlistId": p_id, "resourceId": {"kind": "youtube#video", "videoId": v_id}}}
        )
        return request.execute()
    except googleapiclient.errors.HttpError as e:
        if e.resp.status == 409:
            st.warning(f"ℹ️ 이미 등재된 영상 건너뜀 (ID: {v_id})")
        else:
            st.error(f"❌ 유튜브 API 오류: {e}")
        return None

# ------------------------------------------------------------------
# 4. 사용자 인터페이스 (UI) 구현부
# ------------------------------------------------------------------
st.header("🎵 곡 등록 센터")
tabs = st.tabs(["📂 1. 악보집 풀다운 메뉴 선택 방식", "✍️ 2. 수동 곡명/링크 직접 입력 방식", "⚙️ 악보집 DB 신규 등록"])

# --- TAB 3: 악보집 신규 연동 ---
with tabs[2]:
    st.subheader("⚙️ 시스템 악보집 데이터베이스 추가 등록")
    with st.form("songbook_register_form", clear_on_submit=True):
        book_name = st.text_input("악보집 이름 명칭", placeholder="예: 중앙성가48")
        book_url = st.text_input("악보집 전체 곡 목록 HTML 주소", placeholder="https://joongangart.kr/joongang48/joongang48.html")
        reg_btn = st.form_submit_button("신규 악보집 연동 및 분석 실행")
        
        if reg_btn and book_name and book_url:
            with st.spinner("🤖 중앙성가 전용 크롤러 엔진 기동 중..."):
                parsed_songs = extract_songs_from_joongang(book_url)
            if parsed_songs:
                st.session_state.songbooks[book_name] = parsed_songs
                st.success(f"✅ '{book_name}' 연동 성공! 총 {len(parsed_songs)}개의 곡이 연동되었습니다.")
                st.rerun()
            else:
                st.error("❌ '번호. 명칭' 패턴 식별 실패. 목록용 전용 메인 HTML 주소를 다시 점검하세요.")

# --- TAB 1: 악보집 풀다운 선택 트랙 (오류 복구 완료) ---
with tabs[0]:
    st.subheader("📂 등록된 악보집에서 편리하게 고르기")
    if not st.session_state.songbooks:
        st.info("ℹ️ 활성화된 악보집이 없습니다. 먼저 우측 [악보집 DB 신규 등록] 탭에서 주소를 빌드해 주세요.")
    else:
        selected_book = st.selectbox("📚 대상 악보집 선택", list(st.session_state.songbooks.keys()))
        
        # 곡 리스트가 정상 정렬되어 드롭다운에 출력되도록 처리
        song_options = sorted(list(st.session_state.songbooks[selected_book].keys()))
        selected_song = st.selectbox("🎶 등록할 곡 선택 (풀다운)", song_options)
        
        corresponding_html_link = st.session_state.songbooks[selected_book][selected_song]
        st.info(f"🎯 매핑된 하위 이동 주소: {corresponding_html_link}")
        
        if st.button("🚀 선택한 곡 최종 목록에 추가"):
            clean_title_only = re.sub(r'^\d+[\s\.\-_:\)]+', '', selected_song).strip()
            new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
            st.session_state.playlist_items.append({"id": new_id, "title": clean_title_only, "url": corresponding_html_link})
            st.success(f"✅ 대기열 등재 완료: {clean_title_only}")
            st.rerun()

# --- TAB 2: 수동 입력 트랙 ---
with tabs[1]:
    st.subheader("✍️ 수동 개별 입력")
    with st.form(key="manual_add_form", clear_on_submit=True):
        manual_title = st.text_input("곡 명칭 직접 입력")
        manual_url = st.text_input("연결 HTML 주소 직접 입력")
        if st.form_submit_button(label="수동 추가") and manual_title and manual_url:
            new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
            st.session_state.playlist_items.append({"id": new_