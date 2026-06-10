import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from streamlit_sortables import sort_items
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ------------------------------------------------------------------
# 1. 초기 세션 상태 및 기본 설정
# ------------------------------------------------------------------
st.set_page_config(page_title="유튜브 플레이리스트 자동화 에이전트", layout="wide")
st.title("🎵 악보집 맞춤형 유튜브 플레이리스트 자동화 에이전트")
st.caption("유튜브 ID: vincent.jbim@gmail.com")

if "playlist_items" not in st.session_state:
    st.session_state.playlist_items = []

if "songbooks" not in st.session_state:
    st.session_state.songbooks = {}

PART_MAPPING = {
    "합창": "Test(합창)",
    "소프": "Test(S)",
    "알토": "Test(A)",
    "테너": "Test(T)",
    "베이스": "Test(B)",
    "반주": "Test(반주)"
}

# ------------------------------------------------------------------
# 2. 🔍 [🚨 구조 현행화] '번호. 명칭' 및 연결 HTML 링크 매핑 함수
# ------------------------------------------------------------------
def extract_songs_from_songbook(songbook_url):
    """
    악보 이미지 우측 'play' 버튼 옆의 '번호. 명칭' 텍스트를 인식하고,
    해당 곡명/번호에 걸려있는 진짜 하위 HTML 주소를 정밀 파싱합니다.
    """
    songs_db = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(songbook_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # 페이지 내의 모든 하이퍼링크 태그 조사
        links = soup.find_all('a')
        
        for link in links:
            text = link.get_text().strip()
            href = link.get('href', '')
            
            if href and not href.startswith('#'):
                # 💡 '번호. 명칭' (예: "1. 시월의 어느 멋진 날에", "05. 하나님의 은혜") 정규식 매칭
                # 숫자 뒤에 점(.)이나 공백이 오고 그 뒤에 곡 제목이 붙는 형태를 추적합니다.
                if re.match(r'^\d+[\s\.\-_:\)]', text) or any(char.isdigit() for char in text[:3]):
                    absolute_song_url = urljoin(songbook_url, href)
                    # 곡명('번호. 명칭')을 Key로, 연결된 html 링크를 Value로 저장
                    songs_db[text] = absolute_song_url
                    
        return songs_db
    except Exception as e:
        st.error(f"❌ 악보집 파싱 중 오류 발생: {e}")
        return None

def deep_extract_youtube_urls(main_html_url):
    """ 메인 HTML 하단 6개 버튼을 추적하여 파트별 진짜 유튜브 링크를 가져옵니다. """
    final_result = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(main_html_url, headers=headers, timeout=10)
        if response.status_code != 200: return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a')
        sub_page_urls = {}
        
        for part_key in PART_MAPPING.keys():
            for link in links:
                link_text = link.get_text().strip()
                link_href = link.get('href', '')
                if part_key in link_text or part_key in link_href:
                    sub_page_urls[part_key] = urljoin(main_html_url, link_href)
                    break
                    
        if len(sub_page_urls) < 6:
            valid_hrefs = [urljoin(main_html_url, l.get('href')) for l in links if l.get('href') and not l.get('href').startswith('#')]
            valid_hrefs = [u for u in list(dict.fromkeys(valid_hrefs)) if u != main_html_url]
            for i, part_key in enumerate(PART_MAPPING.keys()):
                if i < len(valid_hrefs) and part_key not in sub_page_urls:
                    sub_page_urls[part_key] = valid_hrefs[i]

        yt_pattern = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
        for part_key, playlist_name in PART_MAPPING.items():
            target_sub_url = sub_page_urls.get(part_key)
            if target_sub_url:
                try:
                    sub_res = requests.get(target_sub_url, headers=headers, timeout=5)
                    found_ids = re.findall(yt_pattern, sub_res.text) if sub_res.status_code == 200 else []
                    final_result[playlist_name] = f"https://www.youtube.com/watch?v={found_ids[0]}" if found_ids else ""
                except: final_result[playlist_name] = ""
            else: final_result[playlist_name] = ""
        return final_result
    except: return None

# 유튜브 API 베이스 함수들
def get_youtube_service():
    try:
        creds = Credentials(token=None, refresh_token=st.secrets["google"]["refresh_token"],
                            token_uri="https://oauth2.googleapis.com/token",
                            client_id=st.secrets["google"]["client_id"], client_secret=st.secrets["google"]["client_secret"])
        return build('youtube', 'v3', credentials=creds)
    except: return None

def extract_video_id(url):
    m = re.search(r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})', url)
    return m.group(1) if m else None

def get_or_create_playlist(youtube, title):
    r = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
    for item in r.get("items", []):
        if item["snippet"]["title"] == title: return item["id"]
    return youtube.playlists().insert(part="snippet,status", body={"snippet": {"title": title, "description": "자동 생성"}, "status": {"privacyStatus": "private"}}).execute()["id"]

def add_video_to_playlist(youtube, p_id, v_id):
    return youtube.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": p_id, "resourceId": {"kind": "youtube#video", "videoId": v_id}}}).execute()


# ------------------------------------------------------------------
# 3. 📖 UI 레이아웃 영역 (풀다운 메뉴 연동 제어)
# ------------------------------------------------------------------
st.header("🎵 곡 등록 센터")
tabs = st.tabs(["📂 1. 악보집 풀다운 메뉴 선택 방식", "✍️ 2. 수동 곡명/링크 직접 입력 방식", "⚙️ 악보집 DB 신규 등록"])

# --- TAB 3: 악보집 등록 ---
with tabs[2]:
    st.subheader("⚙️ 시스템 악보집 데이터베이스 추가 등록")
    with st.form("songbook_register_form", clear_on_submit=True):
        book_name = st.text_input("악보집 이름 명칭", placeholder="예: 2026년 봄 정기연합 찬양집")
        book_url = st.text_input("악보집 전체 곡 목록 HTML 주소", placeholder="http://domain.com/index_list.html")
        reg_btn = st.form_submit_button("신규 악보집 연동 및 분석 실행")
        
        if reg_btn and book_name and book_url:
            with st.spinner("🤖 play 버튼 옆의 '번호. 명칭' 및 연결된 HTML 링크 추출 중..."):
                parsed_songs = extract_songs_from_songbook(book_url)
            if parsed_songs:
                st.session_state.songbooks[book_name] = parsed_songs
                st.success(f"✅ '{book_name}' 연동 완료! 총 {len(parsed_songs)}개의 곡 목록과 하위 링크 매핑 데이터가 내장되었습니다.")
            else:
                st.error("❌ '번호. 명칭' 패턴 또는 연결 하이퍼링크를 찾지 못했습니다. 주소를 다시 확인해 주세요.")

# --- TAB 1: 악보집 풀다운 선택 (요청하신 핵심 핵심 로직 구현부) ---
with tabs[0]:
    st.subheader("📂 등록된 악보집에서 편리하게 고르기")
    if not st.session_state.songbooks:
        st.info("ℹ️ 활성화된 악보집이 없습니다. [악보집 DB 신규 등록] 탭에서 악보집 주소를 먼저 연동해 주세요.")
    else:
        selected_book = st.selectbox("📚 대상 악보집 선택", list(st.session_state.songbooks.keys()))
        
        # '번호. 명칭'으로 파싱된 리스트가 풀다운 메뉴에 정렬되어 노출됩니다.
        song_options = list(st.session_state.songbooks[selected_book].keys())
        selected_song = st.selectbox("🎶 등록할 곡 선택 (풀다운)", song_options)
        
        # 사용자가 곡을 고르면 자동으로 연치된 하위 HTML 링크가 매핑됩니다.
        corresponding_html_link = st.session_state.songbooks[selected_book][selected_song]
        st.caption(f"🔗 매핑된 하위 HTML 주소: {corresponding_html_link}")
        
        if st.button("🚀 선택한 곡 최종 목록에 추가"):
            new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
            # 목록에 추가할 때 곡명과 함께 연동된 진짜 html link를 셋으로 묶어 세션에 주입
            st.session_state.playlist_items.append({
                "id": new_id, 
                "title": selected_song, 
                "url": corresponding_html_link
            })
            st.success(f"✅ 등재 완료: {selected_song}")
            st.rerun()

# --- TAB 2: 수동 입력 ---
with tabs[1]:
    st.subheader("✍️ 수동 개별 입력")
    with st.form(key="manual_add_form", clear_on_submit=True):
        col1, col2 = st.columns([2, 3])
        with col1: manual_title = st.text_input("곡 명칭 직접 입력")
        with col2: manual_url = st.text_input("메인 HTML Link 주소 직접 입력")
        if st.form_submit_button(label="수동 추가") and manual_title and manual_url:
            new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
            st.session_state.playlist_items.append({"id": new_id, "title": manual_title, "url": manual_url})
            st.success("✅ 수동 입력 건이 등재 목록에 추가되었습니다.")
            st.rerun()

# ------------------------------------------------------------------
# 4. 최종 빌드 대기열 목록 및 5. 원클릭 자동 연동 실행부
# ------------------------------------------------------------------
st.divider()
st.subheader("📋 현재 Playlist 등재 목록 및 순서 조정")

if not st.session_state.playlist_items:
    st.warning("현재 대기열에 등록된 곡이 없습니다. 위 트랙 중 하나를 이용해 곡을 빌드해 주세요.")
else:
    display_list = [f"☰  {item['title']}  |  🌐 연동 링크: {item['url']}" for item in st.session_state.playlist_items]
    sorted_display_list = sort_items(display_list)
    
    updated_items = []
    for display_text in sorted_display_list:
        clean_title = display_text.replace("☰  ", "").split("  |  🌐 연동 링크:")[0]
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

    st.divider()
    st.subheader("⚙️ 플레이리스트 원클릭 자동 반영")
    
    if st.button("✨ Playlist에 반영 (이동 및 추출 100% 자동화)", type="primary", use_container_width=True):
        youtube = get_youtube_service()
        if youtube:
            for item in st.session_state.playlist_items:
                st.markdown(f"### 📂 곡명: **{item['title']}** 분석 및 등록")
                with st.status("🤖 하위 링크 분석 및 유튜브 원본 링크 추출 중...", expanded=True) as status:
                    extracted_part_urls = deep_extract_youtube_urls(item["url"])
                    status.update(label="🧬 6개 파트 주소 추출 완료!", state="complete")
                
                if extracted_part_urls:
                    for playlist_name, url in extracted_part_urls.items():
                        if url:
                            video_id = extract_video_id(url)
                            if video_id:
                                with st.spinner(f"'{playlist_name}'에 등록 중..."):
                                    p_id = get_or_create_playlist(youtube, playlist_name)
                                    add_video_to_playlist(youtube, p_id, video_id)
                                st.success(f"✅ [{playlist_name}] 등록 성공! ➡️ {url}")
            st.balloons()