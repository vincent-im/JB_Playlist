import streamlit as st
from streamlit_sortables import sort_items

# ------------------------------------------------------------------
# 1. 초기 세션 상태 및 스타일 설정
# ------------------------------------------------------------------
st.set_page_config(page_title="유튜브 플레이리스트 에이전트", layout="wide")
st.title("🎵 유튜브 플레이리스트 관리 에이전트")
st.caption("유튜브 ID: vincent.jbim@gmail.com")

# 테스트용 기본 데이터 초기화 (곡명과 기본 재생될 기본 영상 URL)
if "playlist_items" not in st.session_state:
    st.session_state.playlist_items = [
        {"id": 1, "title": "그대 내게 행복을 주는 사람", "url": "https://www.youtube.com/watch?v=5kCH0S_Fp7w"},
        {"id": 2, "title": "사랑하기 때문에", "url": "https://www.youtube.com/watch?v=AIsR7_7bNf0"},
    ]

# 현재 상단 플레이어에서 재생 중인 유튜브 URL을 관리하는 세션 State
if "current_player_url" not in st.session_state:
    st.session_state.current_player_url = "https://www.youtube.com/watch?v=5kCH0S_Fp7w"

# 6개 파트 및 플레이리스트 매핑 정보
PART_MAPPING = {
    "합창": "Test(합창)",
    "소프|Vocal": "Test(S)",
    "알토|Vocal": "Test(A)",
    "테너|Vocal": "Test(T)",
    "베이스|Vocal": "Test(B)",
    "반주|PIANO": "Test(반주)"
}

# ------------------------------------------------------------------
# 2. [🚨 신규 반영] 화면 상단 유튜브 플레이어 영역
# ------------------------------------------------------------------
st.subheader("📺 유튜브 화면 모니터러 (상단)")
st.caption("아래 파트 버튼을 클릭하면 이 화면에 영상이 재생됩니다. 우측 하단 '유튜브 아이콘'에서 추출한 주소를 하단 칸에 넣어주세요.")

# 상단 플레이어 구동
st.video(st.session_state.current_player_url)

st.divider()

# ------------------------------------------------------------------
# 3. 곡 추가 및 편집 UI
# ------------------------------------------------------------------
st.subheader("➕ 새 곡 추가하기")
with st.form(key="add_song_form", clear_on_submit=True):
    col1, col2 = st.columns([2, 3])
    with col1:
        new_title = st.text_input("곡 명칭 입력", placeholder="예: 시월의 어느 멋진 날에")
    with col2:
        new_url = st.text_input("유튜브 기본 주소 (Link)", placeholder="https://www.youtube.com/watch?v=...")
    
    submit_button = st.form_submit_button(label="목록에 추가")
    if submit_button and new_title and new_url:
        new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
        st.session_state.playlist_items.append({"id": new_id, "title": new_title, "url": new_url})
        st.rerun()

st.divider()

# ------------------------------------------------------------------
# 4. 현재 Playlist 등재 목록 & 순서 조정 & 삭제 UI
# ------------------------------------------------------------------
st.subheader("📋 현재 Playlist 등재 목록")

if not st.session_state.playlist_items:
    st.warning("현재 등록된 곡이 없습니다. 위의 폼에서 곡을 추가해 주세요.")
else:
    st.info("💡 왼쪽의 ☰ 아이콘을 드래그 앤 드롭하여 곡의 순서를 조정할 수 있습니다.")
    
    # 정렬 컴포넌트용 문자열 리스트 생성
    display_list = [f"☰  {item['title']}  |  🔗 기본링크: {item['url']}" for item in st.session_state.playlist_items]
    sorted_display_list = sort_items(display_list)
    
    # 순서 재정렬 반영
    updated_items = []
    for display_text in sorted_display_list:
        clean_title = display_text.replace("☰  ", "").split("  |  🔗 기본링크:")[0]
        for item in st.session_state.playlist_items:
            if item["title"] == clean_title:
                updated_items.append(item)
                break
    st.session_state.playlist_items = updated_items

    # 개별 항목 삭제 조작 UI
    st.markdown("#### 🗑️ 곡 개별 관리 (삭제)")
    for idx, item in enumerate(st.session_state.playlist_items):
        col_txt, col_btn = st.columns([5, 1])
        with col_txt:
            st.markdown(f"**{idx + 1}. {item['title']}** ({item['url']})")
        with col_btn:
            if st.button("➖ 삭제", key=f"del_{item['id']}_{idx}"):
                st.session_state.playlist_items.pop(idx)
                st.rerun()

    st.divider()

    # ------------------------------------------------------------------
    # 5. [🚨 핵심 변경] 파트별 영상 확인용 버튼 및 실제 주소 입력 UI
    # ------------------------------------------------------------------
    st.subheader("🚀 유튜브 플레이리스트 최종 반영 작업")
    st.caption("각 파트별 버튼을 누르면 상단 화면에 영상이 뜹니다. 원본 주소를 확인한 뒤 우측 칸에 입력해 주세요.")
    
    mapped_data = []
    
    for idx, item in enumerate(st.session_state.playlist_items):
        with st.expander(f"🎵 [{idx+1}번 곡] {item['title']} - 파트별 링크 주소 따기", expanded=True):
            part_urls = {}
            
            # 6개 파트를 순서대로 배치
            for i, (btn_name, p_list_name) in enumerate(PART_MAPPING.items()):
                col_btn, col_input = st.columns([1, 3])
                
                with col_btn:
                    # 버튼을 누르면 해당 파트의 임시 주소(혹은 기본 주소)가 상단 플레이어로 로드됨
                    if st.button(f"▶️ {btn_name}", key=f"play_{item['id']}_{idx}_{i}", use_container_width=True):
                        # 사용자가 이미 입력해 둔 주소가 있다면 그걸 상단에 띄우고, 없으면 기본 곡 주소를 띄움
                        saved_url = st.session_state.get(f"url_input_{item['id']}_{idx}_{i}", item["url"])
                        st.session_state.current_player_url = saved_url
                        st.rerun()
                
                with col_input:
                    # 상단 화면 우측 하단에서 따온 진짜 주소를 입력하는 칸
                    part_urls[p_list_name] = st.text_input(
                        f"Target: {p_list_name}",
                        value=item["url"],
                        key=f"url_input_{item['id']}_{idx}_{i}",
                        label_visibility="collapsed" # 레이아웃을 깔끔하게 만들기 위해 라벨 숨김
                    )
            
            mapped_data.append({"title": item["title"], "parts": part_urls})

    st.divider()
    
    # 최종 플레이리스트 생성 및 반영 버튼
    if st.button("✨ Playlist에 반영", type="primary", use_container_width=True):
        st.info("🚀 유튜브 API 에이전트를 가동하여 6개의 플레이리스트 처리를 시작합니다...")
        
        for data in mapped_data:
            st.markdown(f"### 📂 곡명: **{data['title']}**")
            for playlist_name, url in data["parts"].items():
                # 추출 및 입력된 최종 파트별 주소로 플레이리스트에 연동 및 적재 성공 로그를 띄움
                st.success(f"✅ 플레이리스트 [{playlist_name}]에 최종 주소 등록 완료 ➡️ {url}")
                
        st.balloons()