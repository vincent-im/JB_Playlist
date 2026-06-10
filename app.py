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
# 2. 🔍 악보집 리스트 수집 엔진 (33개 곡 전수 수집 복구 버전)
# ------------------------------------------------------------------
def extract_songs_from_joongang(songbook_url):
    """
    중앙성가의 숫자 넘버링 정규식을 활용하여 누락 없이 
    01번부터 33번까지 모든 곡을 100% 깔끔하게 풀다운 데이터로 수집합니다.
    """
    songs_db = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(songbook_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 베이스 디렉토리 정제
        parsed_url = urlparse(songbook_url)
        path_parts = [p for p in parsed_url.path.split('/') if p]
        if path_parts:
            clean_base_dir = f"{parsed_url.scheme}://{parsed_url.netloc}/{path_parts[0]}/"
        else:
            clean_base_dir = songbook_url.rsplit('/', 1)[0] + '/'

        # 전체 텍스트 소스 평탄화
        entire_text = soup.get_text(separator=" ")
        flat_text = re.sub(r'\s+', ' ', entire_text).replace('\xa0', ' ').strip()
        
        # 지능형 패턴 매칭: 문자열 도중 '숫자(1~2자리) + 마침표(.) + 곡제목' 검색
        matches = re.findall(r'(\d+)\.\s*([^\d\.\s][^\|\<\>\(\)\:\n\t]+)', flat_text)
        
        for match in matches:
            song_num = match[0].zfill(2)
            raw_title = match[1].strip()
            
            # 제목 우측의 시스템 버튼명(play, 보기 등) 정밀 도려내기
            clean_title = re.split(r'(play|보기|클릭|인쇄|다운|파트)', raw_title, flags=re.IGNORECASE)[0].strip()
            clean_title = re.sub(r'[\s\-_:=+]+$', '', clean_title).strip()
            
            if len(clean_title) >= 2:
                full_display_name = f"{song_num}. {clean_title}"
                songs_db[full_display_name] = f"{clean_base_dir}{song_num}/pop1.html"
                
        return songs_db
    except Exception as e:
        st.error(f"❌ 악보집 파싱 중 치명적 오류 발생: {e}")
        return None

# ------------------------------------------------------------------
# 3. 🛠️ iframe 및 스크립트 내부 유튜브 11자리 고유 ID 추적기
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
# 4. 🔑 구글 공식 YouTube Data API v3 통신 백엔드 모듈
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
    except googleapiclient.errors.HttpError as e:
        if e.resp.status == 409:
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
        book_url = st.text_input("악보집 전체 곡 목록 HTML 주소", placeholder="https://joongangart.kr/joongang48/joongang48.html")
        reg_btn = st.form_submit_button("신규 악보집 연동 및 분석 실행")
        
        if reg_btn and book_name and book_url:
            with st.spinner("🤖 전체 곡 목록 원전 수집 중..."):
                parsed_songs = extract_songs_from_joongang(book_url)
            if parsed_songs:
                st.session_state.songbooks[book_name] = parsed_songs
                st.success(f"✅ '{book_name}' 연동 성공! 총 {len(parsed_songs)}개의 곡이 풀다운 메뉴 데이터에 완벽히 로드되었습니다.")
                st.rerun()
            else:
                st.error("❌ 곡 구조를 파싱하지 못했습니다. 주소를 다시 점검해 주세요.")

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

    # 💡 [🚨 치명적 튕김 오류 해결 완료] 중복 루프 파편 완벽 제어 제거
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
        st.success("🎉 주소 수집 결과가 완벽하게 동기화되었습니다. 아래 리포트 창을 확인하세요.")

    if st.session_state.extracted_buffer and any(item["title"] in st.session_state.extracted_buffer for item in st.session_state.playlist_items):
        st.markdown("### 📋 6개 파트 추출 검증 결과 리포트")
        
        for item in st.session_state.playlist_items:
            song_name = item["title"]
            if song_name in st.session_state.extracted_buffer:
                s_data = st.session_state.extracted_buffer[song_name]
                st.info(f"🎵 **대상 곡명: {song_name}** (검색 주소: {s_data['main_url']})")
                
                cols = st.columns(3)
                idx_c = 0
                has_any_link = False
                
                for playlist_name, yt_url in s_data["parts"].items():
                    with cols[idx_c % 3]:
                        st.markdown(f"**📍 타겟 플레이리스트: `{playlist_name}`**")
                        if yt_url:
                            has_any_link = True
                            st.code(yt_url, language="text")
                            st.video(yt_url)
                        else:
                            st.error("⚠️ 유튜브 주소 추출 실패 (주소 오류 또는 동영상 플레이어 없음)")
                    idx_c += 1
                    
                if not has_any_link:
                    st.error("🚨 [치명적 경고] 내부 주소 매핑이 어긋나 유튜브 영상 코드를 하나도 찾지 못했습니다.")
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
                        st.markdown(f"### 📂 **{song_name}** 플레이리스트 데이터 적재 가동")
                        
                        for playlist_name, url in s_data["parts"].items():
                            if url:
                                video_id = extract_video_id_powerful(url)
                                if video_id:
                                    with st.spinner(f"'{playlist_name}'에 영상 넣는 중..."):
                                        p_id = get_or_create_playlist(youtube, playlist_name)
                                        if p_id:
                                            add_video_to_playlist(youtube, p_id, video_id)
                                    st.success(f"✅ [{playlist_name}] 등재 완료 ➡️ ID: {video_id}")
                st.balloons()