import streamlit as st
from streamlit_sortables import sort_items
import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

# ------------------------------------------------------------------
# 1. 초기 세션 상태(Session State) 및 임시 데이터 설정
# ------------------------------------------------------------------
st.set_page_config(page_title="유튜브 플레이리스트 에이전트", layout="wide")
st.title("🎵 유튜브 플레이리스트 관리 에이전트")
st.caption("계정: vincent.jbim@gmail.com")

# 임시 데이터 초기화 (유튜브 API 연동 전 테스트용 기본 데이터)
if "playlist_items" not in st.session_state:
    st.session_state.playlist_items = [
        {"id": 1, "title": "그대 내게 행복을 주는 사람", "url": "https://www.youtube.com/watch?v=example1"},
        {"id": 2, "title": "사랑하기 때문에", "url": "https://www.youtube.com/watch?v=example2"},
    ]

# 매핑 정보 (파트별 버튼 명칭 및 타겟 플레이리스트)
PART_MAPPING = {
    "합창": "Test(합창)",
    "소프|Vocal": "Test(S)",
    "알토|Vocal": "Test(A)",
    "테너|Vocal": "Test(T)",
    "베이스|Vocal": "Test(B)",
    "반주|PIANO": "Test(반주)"
}

# ------------------------------------------------------------------
# 2. 유튜브 API 연동 함수 (기본 틀)
# ------------------------------------------------------------------
def get_youtube_client():
    """유튜브 API 인증 및 클라이언트 반환"""
    # ⚠️ 주의: GitHub 연동 시 client_secret.json과 token.json은 .gitignore에 등록해야 합니다.
    scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
    api_service_name = "youtube"
    api_version = "3"
    client_secrets_file = "client_secret.json"

    # 로컬 테스트 및 Streamlit Deployment 환경에 맞게 OAuth2 분기 처리가 필요합니다.
    # 여기서는 개념 검증(PoC)을 위한 기본 구조만 제안합니다.
    if os.path.exists(client_secrets_file):
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
            client_secrets_file, scopes)
        credentials = flow.run_local_server(port=0)
        return googleapiclient.discovery.build(api_service_name, api_version, credentials=credentials)
    return None

def add_video_to_playlist(youtube, playlist_name, video_url):
    """특정 플레이리스트 이름을 찾아 영상을 추가하는 로직 (가상 함수)"""
    st.write(f"🔄 '{playlist_name}' 플레이리스트에 영상 추가 중: {video_url}")
    # [실제 구현 시 포함될 API 로직 흐름]
    # 1. youtube.playlists().list(mine=True)로 플레이리스트 목록 검색
    # 2. playlist_name과 일치하는 플레이리스트의 ID(Id) 추출 (없으면 생성)
    # 3. 비디오 URL에서 Video ID 추출 (예: watch?v=XXXXXX)
    # 4. youtube.playlistItems().insert(...)를 통해 비디오 추가


# ------------------------------------------------------------------
# 3. UI 구현: 곡 추가 및 순서 조정
# ------------------------------------------------------------------

### 3-1. 신규 곡 추가 UI
st.subheader("➕ 새 곡 추가하기")
with st.form(key="add_song_form", clear_on_submit=True):
    col1, col2 = st.columns([2, 3])
    with col1:
        new_title = st.text_input("곡 명칭 입력")
    with col2:
        new_url = st.text_input("유튜브 기본 Link 주소")
    
    submit_button = st.form_submit_with_rows_action = st.form_submit_button(label="목록에 추가")
    if submit_button and new_title and new_url:
        new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
        st.session_state.playlist_items.append({"id": new_id, "title": new_title, "url": new_url})
        st.rerun()

---

### 3-2. 현재 Playlist 목록 표시 및 편집 (순서 조정, 삭제)
st.subheader("📋 현재 Playlist 등재 목록")
st.info("💡 좌측의 ☰ 아이콘을 드래그하여 곡 순서를 조정할 수 있습니다.")

# streamlit-sortables를 위한 데이터 포맷 변환 (표시용 문자열 리스트 생성)
display_list = [f"☰  {item['title']} 🔗 ({item['url']})" for item in st.session_state.playlist_items]

# 드래그 앤 드롭 정렬 컴포넌트
sorted_display_list = sort_items(display_list)

# 정렬된 결과 반영하여 세션 상태 업데이트
updated_items = []
for display_text in sorted_display_list:
    # 문자열 파싱을 통해 원래 아이템 매칭
    title_part = display_text.replace("☰  ", "").split(" 🔗 (")[0]
    for item in st.session_state.playlist_items:
        if item["title"] == title_part:
            updated_items.append(item)
            break
st.session_state.playlist_items = updated_items

# 개별 곡 삭제(-) 기능 인터페이스
st.markdown("#### 🗑️ 곡 개별 삭제")
for idx, item in enumerate(st.session_state.playlist_items):
    col_del_text, col_del_btn = st.columns([5, 1])
    with col_del_text:
        st.text(f"{idx+1}. {item['title']}")
    with col_del_btn:
        if st.button("➖ 삭제", key=f"del_{item['id']}"):
            st.session_state.playlist_items.pop(idx)
            st.rerun()

---

# ------------------------------------------------------------------
# 4. Playlist 반영 및 파트별 URL 입력 세션
# ------------------------------------------------------------------
st.subheader("🚀 유튜브 플레이리스트 최종 반영 작업")

if not st.session_state.playlist_items:
    st.warning("등록된 곡이 없습니다. 먼저 곡을 추가해 주세요.")
else:
    st.markdown("#### 1️⃣ 각 파트별 영상 링크 매핑")
    st.caption("반영 대상 곡 목록 순서대로 각 파트 버튼 클릭 시 상단에 뜰 유튜브 영상 주소를 순서대로 적어주세요.")
    
    # 각 곡별로 6가지 파트의 URL을 입력받을 수 있는 입력 창 서포트
    mapped_data = []
    
    for idx, item in enumerate(st.session_state.playlist_items):
        with st.expander(f"🎵 [{idx+1}번 곡] {item['title']} - 파트별 상세 링크 설정", expanded=True):
            part_urls = {}
            cols = st.columns(3) # 레이아웃 정돈을 위해 3열로 배치
            
            for i, (btn_name, p_list_name) in enumerate(PART_MAPPING.items()):
                with cols[i % 3]:
                    # 기본적으로 등록된 메인 url을 넣어두고, 사용자가 파트별로 수정할 수 있게 함
                    part_urls[p_list_name] = st.text_input(
                        f"🔘 {btn_name}", 
                        value=item["url"], 
                        key=f"url_{item['id']}_{btn_name}"
                    )
            mapped_data.append({"title": item["title"], "parts": part_urls})

    st.markdown("---")
    
    # 최종 반영 버튼
    if st.button("✨ Playlist에 반영", type="primary", use_container_width=True):
        st.loading = st.info("유튜브 API 연동 및 플레이리스트 반영 작업을 시작합니다...")
        
        # 실제 API 구동 시 아래 주석 해제
        # youtube = get_youtube_client()
        
        # 시뮬레이션 결과 출력
        for data in mapped_data:
            st.write(f"### 📂 곡명: {data['title']} 처리 중...")
            for playlist_name, url in data["parts"].items():
                # 실제 반영 로직 호출부
                # if youtube: add_video_to_playlist(youtube, playlist_name, url)
                st.success(f"✅ [{playlist_name}] 에 영상 추가 완료 예정 -> {url}")
                
        st.balloons()