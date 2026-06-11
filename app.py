import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
from streamlit_sortables import sort_items
import time
import json

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
# 3. 유튜브 데이터 연동 백엔드 파이프라인
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
# 4. UI 렌더링 파트
# ------------------------------------------------------------------

# 💡 [요청 사항 1]: 'Playlist 편집' 제목 추가 및 폰트 축소 동기화
st.markdown("##### 📝 Playlist 편집")
st.caption("📍 타겟 마스터 기준 리스트: vincent.jbim@gmail.com ➡️ `Test(합창)`")

# 자바스크립트 드래그앤드롭 이벤트 수신 데이터 핸들러
if "drag_dropped_action" in st.query_params:
    action_data = json.loads(st.query_params["drag_dropped_action"])
    action_type = action_data.get("type")
    
    if action_type == "reorder":
        new_order_ids = action_data.get("order", [])
        reordered_items = []
        for s_id in new_order_ids:
            for item in st.session_state.playlist_items:
                if str(item["id"]) == str(s_id):
                    reordered_items.append(item)
                    break
        st.session_state.playlist_items = reordered_items
    
    elif action_type == "delete":
        del_target_id = action_data.get("id")
        # 💡 [요청 사항]: 제거 시 대기열 목록 및 6개 파트 추출 버퍼 세션 데이터베이스에서 영구 동시 삭제
        filtered_items = [item for item in st.session_state.playlist_items if str(item["id"]) != str(del_target_id)]
        for item in st.session_state.playlist_items:
            if str(item["id"]) == str(del_target_id):
                if item["title"] in st.session_state.extracted_buffer:
                    del st.session_state.extracted_buffer[item["title"]]
        st.session_state.playlist_items = filtered_items
        
    st.query_params.clear()
    st.rerun()

# HTML5 Advanced Drag & Drop 컴포넌트 빌드
if not st.session_state.playlist_items:
    st.info("현재 대기열에 등록된 곡이 없습니다. 아래 '곡 등록'에서 곡을 추가해 주세요.")
else:
    # 정빈님이 요청하신 '곡명 앞 3줄(☰) 핸들' 및 '하단 드래그앤드롭 전용 휴지통 마크' 가동
    list_items_html = ""
    for item in st.session_state.playlist_items:
        list_items_html += f"""
        <div class="draggable-song-item" draggable="true" data-id="{item['id']}" style="padding: 10px; margin-bottom: 8px; background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 4px; display: flex; align-items: center; cursor: grab;">
            <span style="font-size: 18px; margin-right: 12px; color: #888; user-select: none;">☰</span>
            <span style="font-weight: bold; font-size: 14px; color: #333;">{item['title']}</span>
            <span style="font-size: 11px; color: #999; margin-left: auto;">{item['url']}</span>
        </div>
        """

    drag_drop_script = f"""
    <div id="drag-sort-container" style="max-width: 100%; font-family: sans-serif;">
        {list_items_html}
        
        <div id="playlist-trash-zone" style="margin-top: 15px; padding: 20px; border: 2px dashed #ff4b4b; background-color: #fff5f5; border-radius: 6px; text-align: center; transition: all 0.2s ease;">
            <span style="font-size: 24px;">🗑️</span>
            <p style="font-size: 13px; color: #ff4b4b; font-weight: bold; margin: 5px 0 0 0;">여기로 곡을 끌어다 놓으면(Drag & Drop) 6개 파트 전체 플레이리스트에서 영구 삭제됩니다.</p>
        </div>
    </div>

    <script>
        const container = document.getElementById('drag-sort-container');
        const trashZone = document.getElementById('playlist-trash-zone');
        let draggedItem = null;

        container.addEventListener('dragstart', (e) => {{
            draggedItem = e.target.closest('.draggable-song-item');
            if (draggedItem) {{
                e.dataTransfer.setData('text/plain', draggedItem.getAttribute('data-id'));
                draggedItem.style.opacity = '0.5';
            }}
        }});

        container.addEventListener('dragend', (e) => {{
            if (draggedItem) {{
                draggedItem.style.opacity = '1';
            }}
            trashZone.style.backgroundColor = '#fff5f5';
            trashZone.style.borderWidth = '2px';
        }});

        container.addEventListener('dragover', (e) => {{
            e.preventDefault();
            const afterElement = getDragAfterElement(container, e.clientY);
            const currentDragged = document.querySelector('.draggable-song-item[style*="opacity: 0.5"]');
            if (currentDragged && e.target.closest('.draggable-song-item') && e.target.closest('#playlist-trash-zone') === null) {{
                if (afterElement == null) {{
                    container.insertBefore(currentDragged, trashZone);
                }} else {{
                    container.insertBefore(currentDragged, afterElement);
                }}
            }}
        }});

        container.addEventListener('drop', (e) => {{
            e.preventDefault();
            if (!draggedItem) return;
            
            // 정렬 순서값 계산 데이터 취합
            const currentItems = container.querySelectorAll('.draggable-song-item');
            const newOrder = [];
            currentItems.forEach(item => {{
                newOrder.push(item.getAttribute('data-id'));
            }});
            
            const data = {{ type: 'reorder', order: newOrder }};
            window.parent.postMessage({{
                st streamlit: 'query_params',
                value: {{ drag_dropped_action: JSON.stringify(data) }}
            }}, '*');
        }});

        // 휴지통 전용 Drag 이벤트 핸들러
        trashZone.addEventListener('dragenter', (e) => {{
            e.preventDefault();
            trashZone.style.backgroundColor = '#ffe3e3';
            trashZone.style.borderWidth = '3px';
        }});

        trashZone.addEventListener('dragover', (e) => {{
            e.preventDefault();
        }});

        trashZone.addEventListener('dragleave', () => {{
            trashZone.style.backgroundColor = '#fff5f5';
            trashZone.style.borderWidth = '2px';
        }});

        trashZone.addEventListener('drop', (e) => {{
            e.preventDefault();
            const itemId = e.dataTransfer.getData('text/plain');
            if (itemId) {{
                const data = {{ type: 'delete', id: itemId }};
                // Streamlit 상위 캐시 엔진으로 다이렉트 쿼리 전송 브릿지 가동
                const parentOrigin = window.location.origin;
                window.parent.postMessage({{
                    type: 'streamlit:set_query_params',
                    queryParams: {{ drag_dropped_action: JSON.stringify(data) }}
                }}, '*');
            }}
        }});

        function getDragAfterElement(container, y) {{
            const dragElements = [...container.querySelectorAll('.draggable-song-item:not([style*="opacity: 0.5"])')];
            return dragElements.reduce((closest, child) => {{
                const box = child.getBoundingClientRect();
                const offset = y - box.top - box.height / 2;
                if (offset < 0 && offset > closest.offset) {{
                    return {{ offset: offset, element: child }};
                }} else {{
                    return closest;
                }}
            }}, {{ offset: Number.NEGATIVE_INFINITY }).element;
        }}
    </script>
    """
    st.components.v1.html(drag_drop_script, height=len(st.session_state.playlist_items) * 65 + 130)

# ------------------------------------------------------------------
# 곡 등록 섹션
# ------------------------------------------------------------------
st.divider()
# 2. '곡 등록' 제목 명칭 및 사이즈 확인 적용
st.markdown("##### 🎵 곡 등록")

# 3. 탭 메뉴 구성
tabs = st.tabs(["📂 악보집에서 선택", "✍️ 수동 입력", "⚙️ 악보집 신규 등록"])

# --- TAB 1: 악보집에서 선택 ---
with tabs[0]:
    st.markdown("<p style='font-size:15px; font-weight:bold; margin-bottom:5px;'>📂 악보집에서 선택</p>", unsafe_allow_html=True)
    if not st.session_state.songbooks:
        st.info("ℹ️ 활성화된 악보집이 없습니다. '악보집 신규 등록' 탭에서 먼저 등록해 주세요.")
    else:
        selected_book = st.selectbox("📚 대상 악보집 선택", list(st.session_state.songbooks.keys()))
        song_options = sorted(list(st.session_state.songbooks[selected_book].keys()))
        selected_song = st.selectbox("🎶 등록할 곡 선택 (풀다운)", song_options)
        
        # 버튼 명칭 변경 최종 반영
        if st.button("🚀 선택한 곡 목록에 추가"):
            clean_title_only = re.sub(r'^\d+[\s\.\-_:\)]+', '', selected_song).strip()
            new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
            st.session_state.playlist_items.append({"id": new_id, "title": clean_title_only, "url": st.session_state.songbooks[selected_book][selected_song]})
            st.success(f"✅ 추가됨: {clean_title_only}")
            st.rerun()

# --- TAB 2: 수동 입력 ---
with tabs[1]:
    st.markdown("<p style='font-size:15px; font-weight:bold; margin-bottom:5px;'>✍️ 수동 입력</p>", unsafe_allow_html=True)
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
    st.markdown("<p style='font-size:15px; font-weight:bold; margin-bottom:5px;'>⚙️ 악보집 신규 등록</p>", unsafe_allow_html=True)
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
# 파트별 가동 연동 최종 적재 제어부
# ------------------------------------------------------------------
st.divider()
st.markdown("#### ⚙️ 파트별 유튜브 추출 및 등재")

if st.button("🔍 1단계: 파트별 주소 추출하기", use_container_width=True):
    if not st.session_state.playlist_items:
        st.error("대기열 목록이 비어있어 추출 작업을 가동할 수 없습니다.")
    else:
        temp_buffer = {}
        for item in st.session_state.playlist_items:
            with st.spinner(f"'{item['title']}' 비디오 찾는 중..."):
                res = deep_extract_youtube_urls(item["url"])
                temp_buffer[item["title"]] = {"main_url": item["url"], "parts": res if res else {}}
        st.session_state.extracted_buffer = temp_buffer
        st.success("추출이 완료되었습니다. 아래 리포트를 확인하세요.")

if st.session_state.extracted_buffer:
    for song_name, data in list(st.session_state.extracted_buffer.items()):
        # 대기열 리스트에 여전히 실존하는 곡인 경우에만 리포트 노출 검증
        if any(item["title"] == song_name for item in st.session_state.playlist_items):
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
            for item in st.session_state.playlist_items:
                song_name = item["title"]
                if song_name in st.session_state.extracted_buffer:
                    data = st.session_state.extracted_buffer[song_name]
                    for p_name, url in data["parts"].items():
                        if url:
                            vid = extract_video_id_powerful(url)
                            if vid:
                                pid = get_or_create_playlist(yt, p_name)
                                add_video_to_playlist(yt, pid, vid)
            st.balloons()