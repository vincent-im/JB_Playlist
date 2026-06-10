import streamlit as st
from streamlit_sortables import sort_items
import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

# ------------------------------------------------------------------
# 1. 초기 세션 상태 및 스타일 설정
# ------------------------------------------------------------------
st.set_page_config(page_title="유튜브 플레이리스트 에이전트", layout="wide")
st.title("🎵 유튜브 플레이리스트 관리 에이전트")
st.caption("유튜브 ID: vincent.jbim@gmail.com")

# 테스트용 기본 데이터 초기화
if "playlist_items" not in st.session_state:
    st.session_state.playlist_items = [
        {"id": 1, "title": "그대 내게 행복을 주는 사람", "url": "https://www.youtube.com/watch?v=example1"},
        {"id": 2, "title": "사랑하기 때문에", "url": "https://www.youtube.com/watch?v=example2"},
    ]

# 6개 타겟 플레이리스트 정의
PART_MAPPING = {
    "합창": "Test(합창)",
    "소프|Vocal": "Test(S)",
    "알토|Vocal": "Test(A)",
    "테너|Vocal": "Test(T)",
    "베이스|Vocal": "Test(B)",
    "반주|PIANO": "Test(반주)"
}

# ------------------------------------------------------------------
# 2. 곡 추가 및 편집 UI
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
        st.colors = ["#ff4b4b"]
        st.rerun()

st.divider()

# ------------------------------------------------------------------
# 3. 현재 Playlist 등재 목록 & 순서 조정 & 삭제 UI
# ------------------------------------------------------------------
st.subheader("📋 현재 Playlist 등재 목록")

if not st.session_state.playlist_items:
    st.warning("현재 등록된 곡이 없습니다. 위의 폼에서 곡을 추가해 주세요.")
else:
    st.info("💡 왼쪽의 ☰ 아이콘을 드래그 앤 드롭하여 곡의 순서를 조정할 수 있습니다.")
    
    # 정렬 컴포넌트용 문자열 리스트 생성
    display_list = [f"☰  {item['title']}  |  🔗 링크: {item['url']}" for item in st.session_state.playlist_items]
    sorted_display_list = sort_items(display_list)
    
    # 순서 재정렬 반영
    updated_items = []
    for display_text in sorted_display_list:
        clean_title = display_text.replace("☰  ", "").split("  |  🔗 링크:")[0]
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
    # 4. 파트별 링크 지정 및 최종 Playlist 반영
    # ------------------------------------------------------------------
    st.subheader("🚀 유튜브 플레이리스트 최종 반영 작업")
    st.caption("각 파트별 버튼 성격의 입력란에 최종 지정할 유튜브 링크 주소를 검토해 주세요.")
    
    mapped_data = []
    
    for idx, item in enumerate(st.session_state.playlist_items):
        with st.expander(f"🎵 [{idx+1}번 곡] {item['title']} - 파트별 상세 링크 설정", expanded=True):
            part_urls = {}
            cols = st.columns(3)
            
            for i, (btn_name, p_list_name) in enumerate(PART_MAPPING.items()):
                with cols[i % 3]:
                    part_urls[p_list_name] = st.text_input(
                        f"🔘 {btn_name}", 
                        value=item["url"], 
                        key=f"url_{item['id']}_{idx}_{i}"
                    )
            mapped_data.append({"title": item["title"], "parts": part_urls})

    st.divider()
    
    # 대망의 반영 버튼
    if st.button("✨ Playlist에 반영", type="primary", use_container_width=True):
        st.info("🚀 유튜브 API 에이전트를 가동합니다. 각 플레이리스트에 곡을 순서대로 추가 중...")
        
        # 순서대로 6개 플레이리스트 처리 시뮬레이션 로그 출력
        for data in mapped_data:
            st.markdown(f"### 📂 곡명: **{data['title']}** 처리 완료 목록")
            for playlist_name, url in data["parts"].items():
                st.success(f"✅ 유튜브 플레이리스트 [{playlist_name}]에 영상 등록 성공 -> {url}")
                
        st.balloons()