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
st.set_page_config(page_title="예본성가대 Playlist 생성", layout="wide")

# 대제목 명칭 및 폰트 사이즈 유지 (H4 수준)
st.markdown("#### 🎼 예본성가대 Playlist 생성")
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
# 2. 🔍 곡 목록 동적 수집 엔진 (범용 파서)
# ------------------------------------------------------------------
def extract_songs_from_joongang(songbook_url):
    songs_db = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    }
    
    parsed_url = urlparse(songbook_url)
    folder_match = re.search(r'/(joongang\d+)/', parsed_url.path, flags=re.IGNORECASE)
    
    if folder_match:
        target_folder = folder_match.group(1)
        clean_base_dir = f"{parsed_url.scheme}://{parsed_url.netloc}/{target_folder}/"
    else:
        clean_base_dir = songbook_url.rsplit('/', 1)[0] + '/'

    try:
        time.sleep(0.3)
        response = requests.get(songbook_url, headers=headers, timeout=12)
        if response.status_code == 200:
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, 'html.parser')
            raw_text_lines = soup.get_text(separator="\n").split('\n')
            for line in raw_text_lines:
                line_clean = line.strip().replace('\xa0', ' ')
                line_clean = re.sub(r'\s+', ' ', line_clean)
                match = re.match(r'^(\d+)\.\s*(.+)$', line_clean)
                if match:
                    song_num = match.group(1).zfill(2)
                    raw_title = match.group(2).strip()
                    clean_title = re.sub(r'\s*(play|보기|클릭|인쇄|다운|파트|듣기|wma|mp3|가사|뮤직).*$', '', raw_title, flags=re.IGNORECASE).strip()
                    clean_title = re.sub(r'[\s\-_:=+.,/]+$', '', clean_title).strip()
                    if len(clean_title) >= 2 and not clean_title.isdigit():
                        full_display_name = f"{song_num}. {clean_title}"
                        songs_db[full_display_name] = f"{clean_base_dir}{song_num}/pop1.html"
    except Exception as e:
        st.error(f"❌ 오류 발생: {e}")
        return None
    return songs_db

# ------------------------------------------------------------------
# 3. 유튜브 추출 및 API 로직 (유지)
# ------------------------------------------------------------------
def extract_video_id_powerful(text_content):
    patterns = [r'v=([a-zA-Z0-9_-]{11})', r'embed/([a-zA-Z0-9_-]{11})', r'youtu\.be/([a-zA-Z0-9_-]{11})']
    for p in patterns:
        m = re.search(p, text_content)
        if m: return m.group(1)
    return None

def deep_extract_youtube_urls(main_html_url):
    final_result = {}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(main_html_url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all(['a', 'area'])
        sub_page_urls = {}
        for part_key in PART_MAPPING.keys():
            for link in links:
                if part_key in link.get_text() or part_key in link.get('href', '') or part_key in link.get('onclick', ''):
                    h = link.get('href', '')
                    if not h:
                        oc = link.get('onclick', '')
                        m = re.search(r'[\'"]([^\'"]+\.html)[\'"]', oc)
                        if m: h = m.group(1)
                    if h: sub_page_urls[part_key] = urljoin(main_html_url, h); break
        for part_key, playlist_name in PART_MAPPING.items():
            u = sub_page_urls.get(part_key)
            if u:
                r = requests.get(u, headers=headers, timeout=5)
                vid = extract_video_id_powerful(r.text)
                final_result[playlist_name] = f"https://www.youtube.com/watch?v={vid}" if vid else ""
            else: final_result[playlist_name] = ""
        return final_result
    except: return None

def get_youtube_service():
    if not HAS_GOOGLE_LIB or "google" not in st.secrets: return None
    creds = Credentials(token=None, refresh_token=st.secrets["google"]["refresh_token"],
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=st.secrets["google"]["client_id"], client_secret=st.secrets["google"]["client_secret"])
    return build('youtube', 'v3', credentials=creds)

def get_or_create_playlist(youtube, title):
    r = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
    for item in r.get("items", []):
        if item["snippet"]["title"] == title: return item["id"]
    return youtube.playlists().insert(part="snippet,status", body={"snippet": {"title": title}, "status": {"privacyStatus": "private"}}).execute()["id"]

def add_video_to_playlist(youtube, p_id, v_id):
    try: youtube.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": p_id, "resourceId": {"kind": "youtube#video", "videoId": v_id}}}).execute()
    except: pass

# ------------------------------------------------------------------
# 4. 사용자 인터페이스 (UI) 구현부
# ------------------------------------------------------------------
st.divider()

# '곡 등록' 타이틀을 H4 수준으로 변경
st.markdown("#### 🎵 곡 등록")

# 탭 메뉴 구성
tabs = st.tabs(["📂 악보집에서 선택", "✍️ 수동 입력", "⚙️ 악보집 신규 등록"])

# --- TAB 1: 악보집에서 선택 ---
with tabs[0]:
    # 내부 제목을 H4(####) 크기로 통일
    st.markdown("#### 📂 악보집에서 선택")
    if not st.session_state.songbooks:
        st.info("ℹ️ 활성화된 악보집이 없습니다. '악보집 신규 등록' 탭에서 먼저 등록해 주세요.")
    else:
        selected_book = st.selectbox("📚 대상 악보집 선택", list(st.session_state.songbooks.keys()))
        song_options = sorted(list(st.session_state.songbooks[selected_book].keys()))
        selected_song = st.selectbox("🎶 등록할 곡 선택 (풀다운)", song_options)
        
        if st.button("🚀 선택한 곡 목록에 추가"):
            clean_title_only = re.sub(r'^\d+[\s\.\-_:\)]+', '', selected_song).strip()
            new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
            st.session_state.playlist_items.append({"id": new_id, "title": clean_title_only, "url": st.session_state.songbooks[selected_book][selected_song]})
            st.success(f"✅ 추가됨: {clean_title_only}")
            st.rerun()

# --- TAB 2: 수동 입력 ---
with tabs[1]:
    # 내부 제목을 H4(####) 크기로 통일
    st.markdown("#### ✍️ 수동 입력")
    with st.form(key="manual_add_form", clear_on_submit=True):
        manual_title = st.text_input("곡 명칭 직접 입력")
        manual_url = st.text_input("연결 HTML 주소 직접 입력")
        if st.form_submit_button(label="수동 추가") and manual_title and manual_url:
            new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
            st.session_state.playlist_items.append({"id": new_id, "title": manual_title.strip(), "url": manual_url.strip()})
            st.success("✅ 대기열에 추가되었습니다.")
            st.rerun()

# --- TAB 3: 악보집 신규 등록 ---
with tabs[2]:
    # 내부 제목을 H4(####) 크기로 통일
    st.markdown("#### ⚙️ 악보집 신규 등록")
    book_name = st.text_input("악보집 이름 (예: 중앙성가48)", key="sb_name_input")
    book_url = st.text_input("악보집 목록 HTML 주소", key="sb_url_input")
    if st.button("신규 악보집 연동 실행", type="primary"):
        if book_name and book_url:
            with st.spinner("분석 중..."):
                parsed_songs = extract_songs_from_joongang(book_url)
            if parsed_songs:
                st.session_state.songbooks[book_name] = parsed_songs
                st.success(f"✅ {book_name} 연동 성공!")
                time.sleep(0.5); st.rerun()
            else: st.error("❌ 파싱 실패. 주소를 확인해 주세요.")

# ------------------------------------------------------------------
# 5, 6. Playlist 등재 목록 및 순서
# ------------------------------------------------------------------
st.divider()
# 목록 타이틀을 H4(####) 크기로 통일
st.markdown("#### 📋 Playlist 등재 목록 및 순서")

if not st.session_state.playlist_items:
    st.warning("현재 대기열에 등록된 곡이 없습니다.")
else:
    display_list = [f"☰ {item['title']}" for item in st.session_state.playlist_items]
    sorted_display_list = sort_items(display_list)
    updated_items = []
    for d in sorted_display_list:
        title = d.replace("☰ ", "")
        for item in st.session_state.playlist_items:
            if item["title"] == title: updated_items.append(item); break
    st.session_state.playlist_items = updated_items

    for idx, item in enumerate(st.session_state.playlist_items):
        c1, c2 = st.columns([8, 1])
        c1.markdown(f"**{idx + 1}. {item['title']}**")
        if c2.button("삭제", key=f"del_{idx}"):
            st.session_state.playlist_items.pop(idx)
            st.rerun()

    # 🚀 최종 가동 섹션
    st.divider()
    # 최종 대분류 타이틀 역시 H4(####) 크기로 매칭하여 통일감 부여
    st.markdown("#### ⚙️ 파트별 유튜브 추출 및 등재")
    if st.button("🔍 1단계: 파트별 주소 추출하기", use_container_width=True):
        temp_buffer = {}
        for item in st.session_state.playlist_items:
            with st.spinner(f"'{item['title']}' 비디오 찾는 중..."):
                res = deep_extract_youtube_urls(item["url"])
                temp_buffer[item["title"]] = {"main_url": item["url"], "parts": res if res else {}}
        st.session_state.extracted_buffer = temp_buffer
        st.success("추출이 완료되었습니다. 아래 리포트를 확인하세요.")

    if st.session_state.extracted_buffer:
        for song_name, data in st.session_state.extracted_buffer.items():
            with st.expander(f"🎵 {song_name} 추출 결과 확인"):
                cols = st.columns(3)
                for i, (p_name, url) in enumerate(data["parts"].items()):
                    with cols[i % 3]:
                        st.caption(f"**{p_name}**")
                        if url: st.video(url)
                        else: st.error("추출 실패")

        if st.button("🚀 2단계: 유튜브 플레이리스트에 최종 등재", type="primary", use_container_width=True):
            yt = get_youtube_service()
            if yt:
                for song_name, data in st.session_state.extracted_buffer.items():
                    for p_name, url in data["parts"].items():
                        if url:
                            vid = extract_video_id_powerful(url)
                            if vid:
                                pid = get_or_create_playlist(yt, p_name)
                                add_video_to_playlist(yt, pid, vid)
                st.balloons()