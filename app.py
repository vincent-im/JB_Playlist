import streamlit as st
import streamlit.components.v1 as components
from streamlit_sortables import sort_items
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import re

# ------------------------------------------------------------------
# 1. 초기 세션 상태 및 기본 설정
# ------------------------------------------------------------------
st.set_page_config(page_title="유튜브 플레이리스트 에이전트", layout="wide")
st.title("🎵 유튜브 플레이리스트 관리 에이전트")
st.caption("유튜브 ID: vincent.jbim@gmail.com")

if "playlist_items" not in st.session_state:
    st.session_state.playlist_items = []

if "current_html_url" not in st.session_state:
    st.session_state.current_html_url = ""

PART_MAPPING = {
    "합창": "Test(합창)",
    "소프|Vocal": "Test(S)",
    "알토|Vocal": "Test(A)",
    "테너|Vocal": "Test(T)",
    "베이스|Vocal": "Test(B)",
    "반주|PIANO": "Test(반주)"
}

# ------------------------------------------------------------------
# 2. 🛠️ 유튜브 API 연동 핵심 백엔드 함수
# ------------------------------------------------------------------
def get_youtube_service():
    """Streamlit Secrets에 저장된 토큰 정보로 유튜브 API 서비스 빌드"""
    try:
        # Streamlit Secrets에서 인증 정보 로드
        creds = Credentials(
            token=None,
            refresh_token=st.secrets["google"]["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=st.secrets["google"]["client_id"],
            client_secret=st.secrets["google"]["client_secret"]
        )
        return build('youtube', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"❌ 구글 API 인증 세팅 에러: {e}. Secrets 설정을 확인하세요.")
        return None

def extract_video_id(url):
    """유튜브 URL에서 11자리 Video ID만 추출하는 정규식 함수"""
    regex = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
    match = re.search(regex, url)
    return match.group(1) if match else None

def get_or_create_playlist(youtube, title):
    """내 계정에 해당 이름의 플레이리스트가 있는지 찾고, 없으면 생성 후 ID 반환"""
    # 1. 기존 플레이리스트 목록 검색
    request = youtube.playlists().list(part="snippet", mine=True, maxResults=50)
    response = request.execute()
    
    for item in response.get("items", []):
        if item["snippet"]["title"] == title:
            return item["id"]
            
    # 2. 일치하는 플레이리스트가 없으면 새로 생성
    create_request = youtube.playlists().insert(
        part="snippet,status",
        body={
          "snippet": {
            "title": title,
            "description": "유튜브 플레이리스트 에이전트에 의해 자동 생성됨"
          },
          "status": {
            "privacyStatus": "private"  # 비공개 생성 (public / unlisted 변경 가능)
          }
        }
    )
    create_response = create_request.execute()
    return create_response["id"]

def add_video_to_playlist(youtube, playlist_id, video_id):
    """특정 플레이리스트 ID에 비디오 ID를 최종 추가"""
    request = youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id
                }
            }
        }
    )
    return request.execute()

# ------------------------------------------------------------------
# 3. 📺 외부 웹페이지 모니터러 영역 (화면 상단 고정)
# ------------------------------------------------------------------
st.subheader("📺 원본 HTML 웹페이지 모니터러 (상단)")
if st.session_state.current_html_url:
    components.iframe(st.session_state.current_html_url, height=450, scrolling=True)
else:
    st.warning("ℹ️ 아래 목록에서 파트 버튼을 누르면 여기에 해당 HTML 웹페이지가 나타납니다.")

st.divider()

# ------------------------------------------------------------------
# 4. ➕ 새 곡 추가 UI
# ------------------------------------------------------------------
st.subheader("➕ 새 곡 추가하기")
with st.form(key="add_song_form", clear_on_submit=True):
    col1, col2 = st.columns([2, 3])
    with col1:
        new_title = st.text_input("곡 명칭 입력")
    with col2:
        new_url = st.text_input("원본 HTML Link 주소 입력")
    
    submit_button = st.form_submit_button(label="목록에 추가")
    if submit_button and new_title and new_url:
        new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
        st.session_state.playlist_items.append({"id": new_id, "title": new_title, "url": new_url})
        if len(st.session_state.playlist_items) == 1:
            st.session_state.current_html_url = new_url
        st.rerun()

st.divider()

# ------------------------------------------------------------------
# 5. 📋 현재 Playlist 등재 목록 (순서 조정 및 삭제)
# ------------------------------------------------------------------
st.subheader("📋 현재 Playlist 등재 목록")
if not st.session_state.playlist_items:
    st.warning("현재 등록된 곡이 없습니다.")
else:
    display_list = [f"☰  {item['title']}  |  🌐 HTML 링크: {item['url']}" for item in st.session_state.playlist_items]
    sorted_display_list = sort_items(display_list)
    
    updated_items = []
    for display_text in sorted_display_list:
        clean_title = display_text.replace("☰  ", "").split("  |  🌐 HTML 링크:")[0]
        for item in st.session_state.playlist_items:
            if item["title"] == clean_title:
                updated_items.append(item)
                break
    st.session_state.playlist_items = updated_items

    for idx, item in enumerate(st.session_state.playlist_items):
        col_txt, col_btn = st.columns([5, 1])
        with col_txt:
            st.markdown(f"**{idx + 1}. {item['title']}** (URL: {item['url']})")
        with col_btn:
            if st.button("➖ 삭제", key=f"del_{item['id']}_{idx}"):
                st.session_state.playlist_items.pop(idx)
                st.rerun()

    st.divider()

    # ------------------------------------------------------------------
    # 6. 🚀 파트별 주소 입력 및 실제 API 반영 버튼 영역
    # ------------------------------------------------------------------
    st.subheader("🚀 유튜브 플레이리스트 최종 반영 작업")
    
    mapped_data = []
    for idx, item in enumerate(st.session_state.playlist_items):
        with st.expander(f"🎵 [{idx+1}번 곡] {item['title']}", expanded=True):
            part_urls = {}
            for i, (btn_name, p_list_name) in enumerate(PART_MAPPING.items()):
                col_btn, col_input = st.columns([1, 3])
                with col_btn:
                    if st.button(f"🔍 {btn_name} 확인", key=f"load_{item['id']}_{idx}_{i}", use_container_width=True):
                        st.session_state.current_html_url = item["url"]
                        st.rerun()
                with col_input:
                    part_urls[p_list_name] = st.text_input(
                        f"Target: {p_list_name}",
                        placeholder="진짜 유튜브 주소(youtube.com/watch?v=...) 붙여넣기",
                        key=f"yt_input_{item['id']}_{idx}_{i}",
                        label_visibility="collapsed"
                    )
            mapped_data.append({"title": item["title"], "parts": part_urls})

    st.divider()
    
    # 대망의 실제 유튜브 API 가동 버튼
    if st.button("✨ Playlist에 반영", type="primary", use_container_width=True):
        st.info("🚀 유튜브 API 에이전트를 가동합니다. 계정 인증 및 등록 절차를 진행합니다...")
        
        # 1. 유튜브 API 클라이언트 호출
        youtube = get_youtube_service()
        
        if youtube:
            # 2. 데이터 순회하며 실시간 적재
            for data in mapped_data:
                st.markdown(f"### 📂 곡명: **{data['title']}** 등록 프로세스 시작")
                for playlist_name, url in data["parts"].items():
                    if url:
                        video_id = extract_video_id(url)
                        if video_id:
                            with st.spinner(f"'{playlist_name}' 작업 처리 중..."):
                                # 플레이리스트 ID 가져오기 (없으면 자동생성)
                                p_id = get_or_create_playlist(youtube, playlist_name)
                                # 비디오 추가
                                add_video_to_playlist(youtube, p_id, video_id)
                            st.success(f"✅ [{playlist_name}] 에 영상 등록 성공! (ID: {video_id})")
                        else:
                            st.error(f"❌ '{url}'에서 올바른 유튜브 비디오 ID를 추출하지 못했습니다.")
                    else:
                        st.warning(f"⚠️ [{playlist_name}] 주소가 입력되지 않아 스킵되었습니다.")
            st.balloons()
            st.success("🎉 모든 플레이리스트 매핑 업무가 성공적으로 끝났습니다!")