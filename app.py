import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
from streamlit_sortables import sort_items
import time

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    import googleapiclient.errors
    HAS_GOOGLE_LIB = True
except ImportError:
    HAS_GOOGLE_LIB = False

# ------------------------------------------------------------------
# 1. 초기 세션 상태 설정 및 앱 기본 환경 정의
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
# 2. 🔍 [🚨 특수공백 및 분절태그 완전 파괴] 범용 곡 목록 동적 수집 엔진
# ------------------------------------------------------------------
def extract_songs_from_joongang(songbook_url):
    """
    HTML 내부의 온갖 지저분한 특수공백(&nbsp;)과 분절 태그들을 완전히 지우고 평탄화하여,
    어떤 성가집이든 원본 주소에서 01번부터 33번까지의 곡 목록을 100% 동적으로 수집합니다.
    """
    songs_db = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    }
    
    # 💡 joongangXX 마스터 폴더를 기준으로 깨끗한 최상위 기반 주소 산출
    parsed_url = urlparse(songbook_url)
    folder_match = re.search(r'/(joongang\d+)/', parsed_url.path, flags=re.IGNORECASE)
    
    if folder_match:
        target_folder = folder_match.group(1)
        clean_base_dir = f"{parsed_url.scheme}://{parsed_url.netloc}/{target_folder}/"
    else:
        clean_base_dir = songbook_url.rsplit('/', 1)[0] + '/'

    try:
        time.sleep(0.3) # 연타 차단 방지 방어선
        response = requests.get(songbook_url, headers=headers, timeout=12)
        
        if response.status_code == 200:
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 💡 [해결의 핵심]: HTML 가짜 공백문자와 줄바꿈을 전부 털어내고 순수 텍스트 스트림으로 병합
            raw_text = soup.get_text(separator=" ")
            
            # 유령 공백(\xa0, &nbsp;)과 멀티 스페이스를 모두 일반 표준 스페이스 1칸으로 완벽 대치
            clean_flat_text = re.sub(r'\s+', ' ', raw_text).replace('\xa0', ' ').strip()
            
            # 💡 숫자와 곡명 사이에 태그나 공백이 찢어놓은 틈새를 완전히 연결하여 찾아내는 정규식 가동
            # 예: "02 . 내 주가 주신 이 노래는" 형태까지 유연하게 전수 검출
            matches = re.findall(r'(\d+)\s*\.?\s*([^\d\.\s][^\|\<\>\(\)\:\t\n]+)', clean_flat_text)
            
            for match in matches:
                song_num = match[0].zfill(2) # "01", "02" 포맷 표준화
                raw_title = match[1].strip()
                
                # 곡 제목 우측의 시스템 기능어(play, 보기, 인쇄 등) 단면 절단 정제
                clean_title = re.split(r'(play|보기|클릭|인쇄|다운|파트|듣기|wma|mp3|가사|성가|중앙|악보)', raw_title, flags=re.IGNORECASE)[0].strip()
                clean_title = re.sub(r'[\s\-_:=+.,/]+$', '', clean_title).strip()
                
                # 유효한 문자열 제목인 경우에만 딕셔너리에 동적 적재
                if len(clean_title) >= 2 and not clean_title.isdigit():
                    # 정빈님이 요청하신 완벽한 '일련번호. 곡명' 규격 수립
                    full_display_name = f"{song_num}. {clean_title}"
                    
                    # 성가집 버전별 하위 페이지 경로 자동 분기 (34집 레거시 subXX.html 완벽 대응)
                    if 'sub' in songbook_url.lower() or '34' in songbook_url:
                        songs_db[full_display_name] = f"{clean_base_dir}sub{song_num}.html"
                    else:
                        songs_db[full_display_name] = f"{clean_base_dir}{song_num}/pop1.html"
                            
    except Exception as e:
        st.error(f"❌ 악보집 주소 동적 파싱 연동 중 치명적 오류 발생: {e}")
        return None

    return songs_db

# ------------------------------------------------------------------
# 3. iframe 및 스크립트 내부 유튜브 11자리 고유 ID 추적기 (기존 정상본 보존)
# ------------------------------------------------------------------
def extract_video_id_powerful(text_content):
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
            if len(vid) == 11 and not any(k in vid.lower() for k in ['http', 'html', 'href', 'scro', 'name', 'col_', 'text', 'java', 'main']):
                return vid
    return None

def deep_extract_youtube_urls(main_html_url):
    final_result = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(main_html_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
            
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all(['a', 'area'])
        sub_page_urls = {}
        
        for part_key in PART_MAPPING.keys():
            for link in links:
                link_text = link.get_text().strip()
                link_href = link.get('href', '')
                link_onclick = link.get('onclick', '')
                
                if part_key in link_text or part_key in link_href or part_key in link_onclick:
                    found_path = link_href
                    if not found_path and link_onclick:
                        path_match = re.search(r'[\'"]([^\'"]+\.html)[\'"]', link_onclick)
                        if path_match:
                            found_path = path_match.group(1)
                            
                    if found_path:
                        sub_page_urls[part_key] = urljoin(main_html_url, found_path)
                        break

        if len(sub_page_urls) < 6:
            all_hrefs = []
            for l in soup.find_all(['a', 'area']):
                h = l.get('href', '')
                oc = l.get('onclick', '')
                if h and '.html' in h and not h.startswith('#'):
                    all_hrefs.append(urljoin(main_html_url, h))
                elif oc and '.html' in oc:
                    pm = re.search(r'[\'"]([^\'"]+\.html)[\'"]', oc)
                    if pm: all_hrefs.append(urljoin(main_html_url, pm.group(1)))
            
            valid_hrefs = [u for u in list(dict.fromkeys(all_hrefs)) if u != main_html_url]
            for i, part_key in enumerate(PART_MAPPING.keys()):
                if i < len(valid_hrefs) and part_key not in sub_page_urls:
                    sub_page_urls[part_key] = valid_hrefs[i]

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
# 4. 🔑 구글 공식 YouTube Data API v3 통신 백엔드 모듈 (원형 유지)
# ------------------------------------------------------------------
def get_youtube_service():
    if not HAS_GOOGLE_LIB:
        st.error("❌ 구글 API 라이브러리가 설치되지 않았습니다.")
        return None
    try:
        if "google" not in st.secrets:
            st.error("❌ Streamlit Secrets 설정이 누락되었습니다.")
            return None
        creds = Credentials(
            token=None, 
            refresh_token=st.secrets["google"]["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=st.secrets["google"]["client_id"], 
            client_secret=st.secrets["google"]["client_secret"]
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
            body={"snippet": {"title": title, "description": "유튜브 에이전트 자동화 생성"}, "status": {"privacyStatus": "private"}}
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
    except Exception as e:
        if "409" in str(e):
            st.warning(f"ℹ️ 플레이리스트에 이미 등재되어 있는 영상입니다. (ID: {v_id})")
        else:
            st.error(f"❌ 유튜브 API 적재 거부 원인: {e}")
        return None

# ------------------------------------------------------------------
# 5. 사용자 인터페이스 (UI) 구현부
# ------------------------------------------------------------------
st.header("🎵 곡 등록 센터")
tabs = st.tabs(["📂 1. 악보집 풀다운 메뉴 선택 방식", "✍️ 2. 수동 곡명/링크 직접 입력 방식", "⚙️ 악보집 DB 신규 등록"])

# --- TAB 3: 악보집 신규 연동 ---
with tabs[2]:
    st.subheader("⚙️ 시스템 악보집 데이터베이스 추가 등록")
    with st.form("songbook_register_form", clear_on_submit=True):
        book_name = st.text_input("악보집 이름 명칭", placeholder="예: 중앙성가48")
        book_url = st.text_input("악보집 전체 곡 목록 HTML 주소", placeholder="https://joongangart.kr/joongang48/01/중앙성가48.html")
        reg_btn = st.form_submit_button("신규 악보집 연동 및 분석 실행")
        
        if reg_btn and book_name and book_url:
            with st.spinner(f"🤖 특수 문자열 공백 완전 분쇄 및 전수 동적 추출 중..."):
                parsed_songs = extract_songs_from_joongang(book_url)
            if parsed_songs and len(parsed_songs) > 0:
                st.session_state.songbooks[book_name] = parsed_songs
                st.success(f"✅ '{book_name}' 연동 성공! 총 {len(parsed_songs)}개의 모든 곡이 '일련번호. 곡명' 규격으로 첫 번째 탭 풀다운 메뉴에 정밀 안착되었습니다.")
            else:
                st.error("❌ 곡 목록 파싱에 실패했습니다. 입력하신 마스터 목차 HTML 주소를 다시 점검해 주십시오.")

# --- TAB 1: 악보집 풀다운 선택형 등록 ---
with tabs[0]:
    st.subheader("📂 등록된 악보집에서 편리하게 고르기")
    if not st.session_state.songbooks:
        st.info("ℹ️ 활성화된 악보집이 없습니다. 먼저 우측 [악보집 DB 신규 등록] 탭에서 주소를 등록해 주세요.")
    else:
        selected_book = st.selectbox("📚 대상 악보집 선택", list(st.session_state.songbooks.keys()))
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
            st.session_state.playlist_items.append({"id": new_id, "title": manual_title.strip(), "url": manual_url.strip()})
            st.success("✅ 대기열에 추가되었습니다.")
            st.rerun()

# ------------------------------------------------------------------
# 6. 📋 현재 Playlist 등재 목록 및 순서 조정
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
                if item["title"] in st.session_state.extracted_buffer:
                    del st.session_state.extracted_buffer[item["title"]]
                st.rerun()

    # ------------------------------------------------------------------
    # 7. 🚀 1단계: 추출 및 시각적 검증 패널
    # ------------------------------------------------------------------
    st.divider()
    st.subheader("⚙️ 1단계: 파트별 유튜브 링크 자동 추출 및 검증")
    
    if st.button("🔍 6개 파트 주소 추출 및 검증하기", type="secondary", use_container_width=True):
        temp_buffer = {}
        for item in st.session_state.playlist_items:
            with st.spinner(f"🤖 '{item['title']}' 하위 6개 파트 비디오 트래킹 및 파싱 중..."):
                res_urls = deep_extract_youtube_urls(item["url"])
                temp_buffer[item["title"]] = {
                    "main_url": item["url"], 
                    "parts": res_urls if res_urls else {p: "" for p in PART_MAPPING.values()}
                }
        st.session_state.extracted_buffer = temp_buffer
        st.success("🎉 주소 수집 결과가 완벽하게 동기화되었습니다.")

    if st.session_state.extracted_buffer and any(item["title"] in st.session_state.extracted_buffer for item in st.session_state.playlist_items):
        st.markdown("### 📋 6개 파트 추출 검증 결과 리포트")
        
        for item in st.session_state.playlist_items:
            song_name = item["title"]
            if song_name in st.session_state.extracted_buffer:
                s_data = st.session_state.extracted_buffer[song_name]
                st.info(f"🎵 **대상 곡명: {song_name}** (검색 주소: {s_data['main_url']})")
                
                cols = st.columns(3)
                idx_c = 0
                
                for playlist_name, yt_url in s_data["parts"].items():
                    with cols[idx_c % 3]:
                        st.markdown(f"**📍 타겟 플레이리스트: `{playlist_name}`**")
                        if yt_url:
                            st.code(yt_url, language="text")
                            st.video(yt_url)
                        else:
                            st.error("⚠️ 유튜브 주소 추출 실패")
                    idx_c += 1
                st.markdown("---")

        # ------------------------------------------------------------------
        # 8. 🚀 2단계: 플레이리스트 최종 업로드 및 구글 서버 적재
        # ------------------------------------------------------------------
        st.subheader("🚀 2단계: 플레이리스트 최종 업로드")
        if st.button("🚀 검증 완료 - 유튜브 플레이리스트에 최종 등재", type="primary", use_container_width=True):
            youtube = get_youtube_service()
            if youtube:
                for item in st.session_state.playlist_items:
                    song_name = item["title"]
                    if song_name in st.session_state.extracted_buffer:
                        s_data = st.session_state.extracted_buffer[song_name]
                        
                        for playlist_name, url in s_data["parts"].items():
                            if url:
                                video_id = extract_video_id_powerful(url)
                                if video_id:
                                    with st.spinner(f"'{playlist_name}'에 영상 넣는 중..."):
                                        p_id = get_or_create_playlist(youtube, playlist_name)
                                        if p_id:
                                            add_video_to_playlist(youtube, p_id, video_id)
                st.balloons()