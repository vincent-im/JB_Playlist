import streamlit as st
import streamlit.components.v1 as components
from streamlit_sortables import sort_items

# ------------------------------------------------------------------
# 1. 초기 세션 상태 및 기본 설정
# ------------------------------------------------------------------
st.set_page_config(page_title="유튜브 플레이리스트 에이전트", layout="wide")
st.title("🎵 유튜브 플레이리스트 관리 에이전트")
st.caption("유튜브 ID: vincent.jbim@gmail.com")

# 플레이리스트 아이템 저장 세션 (예시 데이터 없이 완전히 비어있음)
if "playlist_items" not in st.session_state:
    st.session_state.playlist_items = []

# 모니터링 영역에 띄울 현재 HTML 웹페이지 링크 관리 세션
if "current_html_url" not in st.session_state:
    st.session_state.current_html_url = ""

# 6개 파트 및 타겟 플레이리스트 매핑 정보
PART_MAPPING = {
    "합창": "Test(합창)",
    "소프|Vocal": "Test(S)",
    "알토|Vocal": "Test(A)",
    "테너|Vocal": "Test(T)",
    "베이스|Vocal": "Test(B)",
    "반주|PIANO": "Test(반주)"
}

# ------------------------------------------------------------------
# 2. 📺 외부 웹페이지 모니터러 영역 (화면 상단 고정)
# ------------------------------------------------------------------
st.subheader("📺 원본 HTML 웹페이지 모니터러 (상단)")
st.caption("아래 파트별 작업 영역에서 버튼을 누르면 해당 곡의 HTML 페이지가 여기에 표시됩니다.")

if st.session_state.current_html_url:
    st.info(f"🌐 현재 로드된 페이지: {st.session_state.current_html_url}")
    # 외부 HTML 웹페이지를 안전하게 브라우저 내에 임베드하여 버튼 클릭 및 유튜브 아이콘 추출이 가능하게 함
    components.iframe(st.session_state.current_html_url, height=500, scrolling=True)
else:
    st.warning("ℹ️ 아래 목록에서 파트 버튼을 누르면 여기에 해당 HTML 웹페이지가 나타납니다.")

st.divider()

# ------------------------------------------------------------------
# 3. ➕ 새 곡 추가 UI (외부 HTML 주소 입력)
# ------------------------------------------------------------------
st.subheader("➕ 새 곡 추가하기")
with st.form(key="add_song_form", clear_on_submit=True):
    col1, col2 = st.columns([2, 3])
    with col1:
        new_title = st.text_input("곡 명칭 입력", placeholder="예: 시월의 어느 멋진 날에")
    with col2:
        new_url = st.text_input("원본 HTML Link 주소 입력", placeholder="http://example.com/choir_page.html")
    
    submit_button = st.form_submit_button(label="목록에 추가")
    if submit_button and new_title and new_url:
        # 고유 ID 생성 및 아이템 추가
        new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
        st.session_state.playlist_items.append({"id": new_id, "title": new_title, "url": new_url})
        
        # 처음 곡이 등록되면 해당 URL을 상단 모니터러 기본값으로 세팅
        if len(st.session_state.playlist_items) == 1:
            st.session_state.current_html_url = new_url
        st.rerun()

st.divider()

# ------------------------------------------------------------------
# 4. 📋 현재 Playlist 등재 목록 (순서 조정 및 삭제)
# ------------------------------------------------------------------
st.subheader("📋 현재 Playlist 등재 목록")

if not st.session_state.playlist_items:
    st.warning("현재 등록된 곡이 없습니다. 위의 폼에서 곡을 먼저 추가해 주세요.")
else:
    st.info("💡 왼쪽의 ☰ 아이콘을 드래그 앤 드롭하여 곡의 순서를 조정할 수 있습니다.")
    
    # 드래그앤드롭 정렬을 위한 표시 텍스트 리스트화
    display_list = [f"☰  {item['title']}  |  🌐 HTML 링크: {item['url']}" for item in st.session_state.playlist_items]
    sorted_display_list = sort_items(display_list)
    
    # 정렬 결과 세션 데이터 리바인딩
    updated_items = []
    for display_text in sorted_display_list:
        clean_title = display_text.replace("☰  ", "").split("  |  🌐 HTML 링크:")[0]
        for item in st.session_state.playlist_items:
            if item["title"] == clean_title:
                updated_items.append(item)
                break
    st.session_state.playlist_items = updated_items

    # 개별 곡 삭제 기능
    st.markdown("#### 🗑️ 곡 개별 관리 (삭제)")
    for idx, item in enumerate(st.session_state.playlist_items):
        col_txt, col_btn = st.columns([5, 1])
        with col_txt:
            st.markdown(f"**{idx + 1}. {item['title']}** (URL: {item['url']})")
        with col_btn:
            if st.button("➖ 삭제", key=f"del_{item['id']}_{idx}"):
                st.session_state.playlist_items.pop(idx)
                if not st.session_state.playlist_items:
                    st.session_state.current_html_url = ""
                st.rerun()

    st.divider()

    # ------------------------------------------------------------------
    # 5. 🚀 파트별 추출 및 유튜브 원본 링크 주소 입력 UI
    # ------------------------------------------------------------------
    st.subheader("🚀 유튜브 플레이리스트 최종 반영 작업")
    st.caption("각 파트 버튼을 누르면 상단에 해당 웹페이지가 열립니다. 가이드에 따라 유튜브 원본 주소를 딴 후 우측에 붙여넣으세요.")
    
    mapped_data = []
    
    for idx, item in enumerate(st.session_state.playlist_items):
        with st.expander(f"🎵 [{idx+1}번 곡] {item['title']} - 파트별 유튜브 주소 입력", expanded=True):
            part_urls = {}
            
            # 파트별 동선 제공 (왼쪽 버튼 클릭 -> 상단 화면 확인 -> 오른쪽 주소창 입력)
            for i, (btn_name, p_list_name) in enumerate(PART_MAPPING.items()):
                col_btn, col_input = st.columns([1, 3])
                
                with col_btn:
                    # 이 버튼을 누르면 해당 곡의 HTML 주소가 상단 iframe으로 로드됩니다.
                    if st.button(f"🔍 {btn_name} 확인", key=f"load_{item['id']}_{idx}_{i}", use_container_width=True):
                        st.session_state.current_html_url = item["url"]
                        st.rerun()
                
                with col_input:
                    # 상단 유튜브 화면 우측 하단 아이콘에서 마우스 오버/클릭으로 추출한 진짜 유튜브 주소를 넣는 곳입니다.
                    part_urls[p_list_name] = st.text_input(
                        f"Target: {p_list_name}",
                        placeholder=f"상단 {btn_name} 영상의 진짜 유튜브 주소(youtube.com/...) 입력",
                        key=f"yt_input_{item['id']}_{idx}_{i}",
                        label_visibility="visible"
                    )
            
            mapped_data.append({"title": item["title"], "parts": part_urls})

    st.divider()
    
    # 최종 플레이리스트 저장/반영 버튼
    if st.button("✨ Playlist에 반영", type="primary", use_container_width=True):
        st.info("🚀 유튜브 API 에이전트를 구동합니다. 추출된 진짜 유튜브 주소들을 플레이리스트에 매핑 중...")
        
        # 최종 결과 출력 (이후 실제 유튜브 API 연동 구문이 들어갈 자리)
        for data in mapped_data:
            st.markdown(f"### 📂 곡명: **{data['title']}**")
            for playlist_name, url in data["parts"].items():
                if url:
                    st.success(f"✅ 플레이리스트 **[{playlist_name}]**에 원본 유튜브 영상 등록 성공! ➡️ {url}")
                else:
                    st.warning(f"⚠️ [{playlist_name}] 주소가 입력되지 않아 건너뛰었습니다.")
                    
        st.balloons()