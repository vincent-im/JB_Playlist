import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
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
# 2. 🔍 [🚨 주소 빌드 버그 수정] 중앙성가 전용 파싱 엔진
# ------------------------------------------------------------------
def extract_songs_from_joongang(songbook_url):
    """
    중앙성가 메인 페이지에서 '번호. 곡명' 구조를 정밀 추출합니다.
    중간에 엉뚱한 숫자가 주소에 끼어들지 않도록 정교하게 포맷팅합니다.
    """
    songs_db = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(songbook_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1차 보안 방어선: 단순 글자가 아닌 진짜 링크(a 태그)를 우선 탐색
        links = soup.find_all('a')
        base_path = songbook_url.rsplit('/', 1)[0] + '/'
        
        # 만약 전체 주소 경로에 joongang48.html 같은 명칭이 있으면 정제
        if base_path.endswith('.html/'):
            base_path = base_path.rsplit('/', 2)[0] + '/'

        for link in links:
            text = link.get_text().strip()
            href = link.get('href', '')
            
            # "01. 나의 힘이 되신 주님" 형태 정밀 추적
            match = re.search(r'^(\d+)\.\s*(.+)$', text)
            if match:
                song_num = match.group(1).zfill(2) # 무조건 2자리 숫자 보장 (01, 02 등)
                song_title = match.group(2)
                full_display_name = f"{song_num}. {song_title}"
                
                # 💡 [버그 수정 핵심] href 주소 자체에 곡 번호가 들어있는지 검증하거나 직접 깨끗하게 조립
                if song_num in href and 'pop1.html' in href:
                    constructed_sub_url = urljoin(songbook_url, href)
                else:
                    # 불필요한 서브경로 결합을 차단하고 최상위 악보집 폴더 경로 기준으로 직접 강제 조립
                    constructed_sub_url = f"{base_path}{song_num}/pop1.html"
                
                songs_db[full_display_name] = constructed_sub_url

        # 만약 a 태그로 수집이 부족할 경우, 전체 텍스트 요소를 활용한 2차 백업 파싱
        if not songs_db:
            all_text_elements = soup.find_all(string=True)
            for element in all_text_elements:
                clean_text = element.strip()
                match = re.search(r'^(\d+)\.\s*(.+)$', clean_text)
                if match:
                    song_num = match.group(1).zfill(2)
                    song_title = match.group(2)
                    full_display_name = f"{song_num}. {song_title}"
                    constructed_sub_url = f"{base_path}{song_num}/pop1.html"
                    songs_db[full_display_name] = constructed_sub_url
                    
        return songs_db
    except Exception as e:
        st.error(f"❌ 악보집 파싱 중 오류 발생: {e}")
        return None

def extract_video_id_powerful(text_content):
    """
    중앙성가 소스코드 내부(embed, iframe src, javascript play함수 내부 파라미터)에 
    숨겨진 11자리 유튜브 고유 ID 패턴을 빈틈없이 역추적합니다.
    """
    patterns = [
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'v=([a-zA-Z0-9_-]{11})',
        r'["\']([a-zA-Z0-9_-]{11})["\']' # 소스코드 내 문자열 변수 추적
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text_content)
        for vid in matches:
            # 유튜브 ID는 정확히 11자리이며, 일반적인 웹 주소 키워드가 아닌 것 필터링
            if len(vid) == 11 and not any(k in vid.lower() for k in ['http', 'html', 'href', 'scro', 'name']):
                return vid
    return None

def deep_extract_youtube_urls(main_html_url):
    """ 각 곡별 하위 페이지(pop1.html) 내부에서 6개 파트를 열어 유튜브 주소를 완벽하게 수집합니다. """
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
        
        # 1단계: 각 파트 버튼 링크 탐색
        for part_key in PART_MAPPING.keys():
            for link in links:
                link_text = link.get_text().strip()
                link_href = link.get('href', '')
                if part_key in link_text or part_key in link_href:
                    sub_page_urls[part_key] = urljoin(main_html_url, link_href)
                    break
                    
        # 2단계: 순서 기반 예외 방어 배열 처리
        if len(sub_page_urls) < 6:
            valid_hrefs = [urljoin(main_html_url, l.get('href')) for l in links if l.get('href') and not l.get('href').startswith('#')]
            valid_hrefs = [u for u in list(dict.fromkeys(valid_hrefs)) if u != main_html_url]
            for i, part_key in enumerate(PART_MAPPING.keys()):
                if i < len(valid_hrefs) and part_key not in sub_page_urls:
                    sub_page_urls[part_key] = valid_hrefs[i]

        # 3단계: 최종 페이지 소스코드에서 강력해진 엔진으로 ID 수집
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
            body={"snippet": {"title": title, "description": "에이전트 시스템 자동 생성"}, "status": {"privacyStatus": "private"}}
        )
        return create_request.execute()["id"]
    except Exception as e:
        st.error(f"❌ 플레이리스트 핸들링 차단 사유: {e}")
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
            st.warning(f"ℹ️ 플레이리스트에 이미 등재된 영상 (ID: {v_id})")
        else:
            st.error(f"❌ 유튜브 적재 API 차단 원인: {e}")
        return None

# ------------------------------------------------------------------
# 4. 사용자 인터페이스 (UI)
# ------------------------------------------------------------------
st.header("🎵 곡 등록 센터")
tabs = st.tabs(["📂 1. 악보집 풀다운 메뉴 선택 방식", "✍️ 2. 수동 곡명/링크 직접 입력 방식", "⚙️ 악보집 DB 신규 등록"])

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
                st.success(f"✅ '{book_name}' 연동 성공! 총 {len(parsed_songs)}개의 곡 리스트 데이터가 이식되었습니다.")
                st.rerun()

with tabs[0]:
    st.subheader("📂 등록된 악보집에서 편리하게 고르기")
    if not st.session_state.songbooks:
        st.info("ℹ️ 활성화된 악보집이 없습니다. 먼저 [악보집 DB 신규 등록] 탭에서 주소를 빌드해 주세요.")
    else:
        selected_book = st.selectbox("📚 대상 악보집 선택", list(st.session_state.songbooks.keys()))
        song_options = sorted(list(st.session_state.songbooks[selected_book].keys()))
        selected_song = st.selectbox("🎶 등록할 곡 선택 (풀다운)", song_options)
        corresponding_html_link = st.session_state.songbooks[selected_book][selected_song]
        
        if st.button("🚀 선택한 곡 최종 목록에 추가"):
            clean_title_only = re.sub(r'^\d+[\s\.\-_:\)]+', '', selected_song).strip()
            new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
            st.session_state.playlist_items.append({"id": new_id, "title": clean_title_only, "url": corresponding_html_link})
            st.success(f"✅ 대기열 등재 완료: {clean_title_only}")
            st.rerun()

with tabs[1]:
    st.subheader("✍️ 수동 개별 입력")
    with st.form(key="manual_add_form", clear_on_submit=True):
        manual_title = st.text_input("곡 명칭 직접 입력")
        manual_url = st.text_input("연결 HTML 주소 직접 입력")
        if st.form_submit_button(label="수동 추가") and manual_title and manual_url:
            new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
            st.session_state.playlist_items.append({"id": new_id, "title": manual_title.strip(), "url": manual_url.strip()})
            st.success("✅ 대기열에 추가되었습니다.")
            st.rerun()

# ------------------------------------------------------------------
# 5. 📋 현재 Playlist 등재 목록 및 순서 조정
# ------------------------------------------------------------------
st.divider()
st.subheader("📋 현재 Playlist 등재 목록 및 순서 조정")

if not st.session_state.playlist_items:
    st.warning("현재 대기열에 등록된 곡이 없습니다.")
else:
    display_list = [f"☰  {item['title']}  |  🌐 매핑 주소: {item['url']}" for item in st.session_state.playlist_items]
    sorted_display_list = sort_items(display_list)
    
    updated_items = []
    for display_text in sorted_display_list:
        clean_title = display_text.replace("☰  ", "").split("  |  🌐 매핑 주소:")[0]
        for item in st.session_state.playlist_items:
            if item["title"] == clean_title:
                updated_items.append(item)
                break
    st.session_state.playlist_items = updated_items

    for idx, item in enumerate(st.session_state.playlist_items):
        col_txt, col_btn = st.columns([5, 1])
        with col_txt: st.markdown(f"**{idx + 1}. {item['title']}** (URL: {item['url']})")
        with col_btn:
            if st.button("➖ 삭제", key=f"del_{item['id']}_{idx}"):
                st.session_state.playlist_items.pop(idx)
                st.rerun()

    # ------------------------------------------------------------------
    # 6. 🚀 검증 패널 및 최종 등재 처리
    # ------------------------------------------------------------------
    st.divider()
    st.subheader("⚙️ 1단계: 파트별 유튜브 링크 자동 추출 및 검증")
    
    if st.button("🔍 6개 파트 주소 추출 및 검증하기", type="secondary", use_container_width=True):
        st.session_state.extracted_buffer = {}
        for item in st.session_state.playlist_items:
            with st.spinner(f"🤖 '{item['title']}' 하위 6개 파트 문서 정밀 파싱 중..."):
                res_urls = deep_extract_youtube_urls(item["url"])
                if res_urls:
                    st.session_state.extracted_buffer[item["title"]] = {"main_url": item["url"], "parts": res_urls}
        st.success("🎉 주소 수집 완료! 아래 리포트 영역에서 검증 결과를 확인하세요.")

    if st.session_state.extracted_buffer:
        st.markdown("### 📋 6개 파트 추출 검증 결과 리포트")
        for song_name, s_data in st.session_state.extracted_buffer.items():
            st.info(f"🎵 **대상 곡명: {song_name}**")
            cols = st.columns(3)
            idx_c = 0
            for playlist_name, yt_url in s_data["parts"].items():
                with cols[idx_c % 3]:
                    st.markdown(f"**📍 타겟 플레이리스트: `{playlist_name}`**")
                    if yt_url:
                        st.code(yt_url, language="text")
                        st.video(yt_url)
                    else:
                        st.error("⚠️ 유튜브 주소 추출 실패 (비어있는 파트이거나 파싱 규격 이탈)")
                idx_c += 1
            st.markdown("---")

        st.subheader("🚀 2단계: 플레이리스트 최종 업로드")
        if st.button("🚀 검증 완료 - 유튜브 플레이리스트에 최종 등재", type="primary", use_container_width=True):
            youtube = get_youtube_service()
            if youtube:
                for song_name, s_data in st.session_state.extracted_buffer.items():
                    st.markdown(f"### 📂 **{song_name}** 플레이리스트 데이터 적재 가동")
                    for playlist_name, url in s_data["parts"].items():
                        if url:
                            video_id = extract_video_id_powerful(url)
                            if video_id:
                                with st.spinner(f"구글 파이프라인 연동 중..."):
                                    p_id = get_or_create_playlist(youtube, playlist_name)
                                    if p_id:
                                        add_video_to_playlist(youtube, p_id, video_id)
                                st.success(f"✅ [{playlist_name}] 등재 완료 ➡️ ID: {video_id}")
                st.balloons()