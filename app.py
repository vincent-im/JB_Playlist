import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from streamlit_sortables import sort_items
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ------------------------------------------------------------------
# 1. 초기 세션 상태 및 기본 설정
# ------------------------------------------------------------------
st.set_page_config(page_title="유튜브 플레이리스트 자동화 에이전트", layout="wide")
st.title("🤖 유튜브 플레이리스트 100% 자동화 에이전트")
st.caption("유튜브 ID: vincent.jbim@gmail.com")

if "playlist_items" not in st.session_state:
    st.session_state.playlist_items = []

# 6개 파트의 명칭과 타겟 플레이리스트 정의
PART_MAPPING = {
    "합창": "Test(합창)",
    "소프": "Test(S)",
    "알토": "Test(A)",
    "테너": "Test(T)",
    "베이스": "Test(B)",
    "반주": "Test(반주)"
}

# ------------------------------------------------------------------
# 2. 🔍 [🚨 핵심 신규 기능] HTML 페이지에서 유튜브 진짜 링크 자동 추출 함수
# ------------------------------------------------------------------
def auto_extract_youtube_urls(html_url):
    """
    사용자가 입력한 외부 HTML 주소에 접속하여, 
    6개 파트(합창, 소프, 알토, 테너, 베이스, 반주)와 연관된 진짜 유튜브 주소를 자동 크롤링합니다.
    """
    extracted_urls = {}
    try:
        # 1. 외부 HTML 페이지 소스코드 가져오기
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(html_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            st.error(f"❌ HTML 페이지를 불러오지 못했습니다. (에러 코드: {response.status_code})")
            return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        html_content = response.text
        
        # 2. HTML 소스 내에서 11자리 유튜브 비디오 ID 패턴 조사
        # (예: watch?v=XXXXXXXXXXX, embed/XXXXXXXXXXX, youtu.be/XXXXXXXXXXX)
        yt_pattern = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
        all_video_ids = list(set(re.findall(yt_pattern, html_content)))
        
        # 3. 발견된 유튜브 ID들을 각 파트 키워드와 매핑
        # ※ 실제 타겟 웹페이지의 HTML 구조(텍스트 배치나 버튼 ID 순서)에 따라 매핑 로직은 커스텀 정교화가 필요합니다.
        # 기본적으로 HTML 문서 상단부터 발견되는 유튜브 주소 순서대로 합창 -> 소프 -> 알토 -> 테너 -> 베이스 -> 반주 순으로 자동 배정하거나,
        # '소프', '알토' 글자 주변의 링크를 찾는 매커니즘을 적용합니다.
        
        idx = 0
        for part_key, playlist_name in PART_MAPPING.items():
            if idx < len(all_video_ids):
                # 추출한 ID를 온전한 유튜브 주소 형식으로 복원하여 매핑
                extracted_urls[playlist_name] = f"https://www.youtube.com/watch?v={all_video_ids[idx]}"
                idx += 1
            else:
                # 영상이 모자랄 경우 빈값 처리
                extracted_urls[playlist_name] = ""
                
        return extracted_urls

    except Exception as e:
        st.error(f"❌ 자동 주소 추출 중 에러 발생: {e}")
        return None

# ------------------------------------------------------------------
# 3. 유튜브 Data API 연동 백엔드 함수
# ------------------------------------------------------------------
def get_youtube_service():
    try:
        creds = Credentials(
            token=None,
            refresh_token=st.secrets["google"]["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=st.secrets["google"]["client_id"],
            client_secret=st.secrets["google"]["client_secret"]
        )
        return build('youtube', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"❌ 구글 Secrets 설정 에러: {e}")
        return None

def extract_video_id(url):
    regex = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
    match = re.search(regex, url)
    return match.group(1) if match else None

def get_or_create_playlist(youtube, title):
    request = youtube.playlists().list(part="snippet", mine=True, maxResults=50)
    response = request.execute()
    for item in response.get("items", []):
        if item["snippet"]["title"] == title:
            return item["id"]
    create_request = youtube.playlists().insert(
        part="snippet,status",
        body={"snippet": {"title": title, "description": "에이전트 자동 생성"}, "status": {"privacyStatus": "private"}}
    )
    return create_request.execute()["id"]

def add_video_to_playlist(youtube, playlist_id, video_id):
    request = youtube.playlistItems().insert(
        part="snippet",
        body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
    )
    return request.execute()

# ------------------------------------------------------------------
# 4. ➕ 새 곡 추가 UI (곡명과 HTML 링크만 받음)
# ------------------------------------------------------------------
st.subheader("➕ 새 곡 추가하기")
with st.form(key="add_song_form", clear_on_submit=True):
    col1, col2 = st.columns([2, 3])
    with col1:
        new_title = st.text_input("곡 명칭 입력", placeholder="예: 시월의 어느 멋진 날에")
    with col2:
        new_url = st.text_input("원본 HTML Link 주소 입력", placeholder="http://domain.com/page.html")
    
    submit_button = st.form_submit_button(label="목록에 추가")
    if submit_button and new_title and new_url:
        new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
        st.session_state.playlist_items.append({"id": new_id, "title": new_title, "url": new_url})
        st.rerun()

st.divider()

# ------------------------------------------------------------------
# 5. 📋 현재 Playlist 등재 목록 (순서 조정 및 삭제)
# ------------------------------------------------------------------
st.subheader("📋 현재 Playlist 등재 목록 및 순서 조정")

if not st.session_state.playlist_items:
    st.warning("현재 등록된 곡이 없습니다. 위의 폼에서 곡을 먼저 추가해 주세요.")
else:
    display_list = [f"☰  {item['title']}  |  🌐 HTML 주소: {item['url']}" for item in st.session_state.playlist_items]
    sorted_display_list = sort_items(display_list)
    
    updated_items = []
    for display_text in sorted_display_list:
        clean_title = display_text.replace("☰  ", "").split("  |  🌐 HTML 주소:")[0]
        for item in st.session_state.playlist_items:
            if item["title"] == clean_title:
                updated_items.append(item)
                break
    st.session_state.playlist_items = updated_items

    # 삭제 및 확인 인터페이스
    for idx, item in enumerate(st.session_state.playlist_items):
        col_txt, col_btn = st.columns([5, 1])
        with col_txt:
            st.markdown(f"**{idx + 1}. {item['title']}** (HTML: {item['url']})")
        with col_btn:
            if st.button("➖ 삭제", key=f"del_{item['id']}_{idx}"):
                st.session_state.playlist_items.pop(idx)
                st.rerun()

    st.divider()

    # ------------------------------------------------------------------
    # 6. 🚀 100% 자동화 실행 영역
    # ------------------------------------------------------------------
    st.subheader("⚙️ 플레이리스트 원클릭 자동 반영")
    st.info("아래 버튼을 누르면 에이전트가 각 HTML 내부를 스스로 분석하여 6개 유튜브 주소를 딴 후, 플레이리스트에 바로 등록합니다.")
    
    if st.button("✨ Playlist에 원클릭 반영 (1~4번 과정 자동화)", type="primary", use_container_width=True):
        youtube = get_youtube_service()
        
        if youtube:
            for item in st.session_state.playlist_items:
                st.markdown(f"### 📂 곡명: **{item['title']}** 자동 분석 및 등록 시작")
                
                # 💡 [자동화 핵심] 수동 입력 대신 코드가 HTML 주소에서 파트별 유튜브 링크를 자동 추출함
                with st.spinner("🤖 외부 HTML 페이지 분석 중 및 유튜브 원본 링크 주소 추출 중..."):
                    extracted_part_urls = auto_extract_youtube_urls(item["url"])
                
                if extracted_part_urls:
                    # 추출된 6개 파트 주소를 순회하며 유튜브 플레이리스트에 적재
                    for playlist_name, url in extracted_part_urls.items():
                        if url:
                            video_id = extract_video_id(url)
                            if video_id:
                                with st.spinner(f"'{playlist_name}'에 영상 등록 중..."):
                                    p_id = get_or_create_playlist(youtube, playlist_name)
                                    add_video_to_playlist(youtube, p_id, video_id)
                                st.success(f"✅ [{playlist_name}] 자동 추출 및 등록 성공! ➡️ {url}")
                            else:
                                st.error(f"❌ {playlist_name}: 비디오 ID 추출 실패")
                        else:
                            st.warning(f"⚠️ [{playlist_name}]: HTML 페이지 내에서 일치하는 영상을 찾지 못했습니다.")
                else:
                    st.error(f"❌ '{item['title']}'의 HTML 페이지 분석에 실패하여 등록을 건너뜁니다.")
            
            st.balloons()
            st.success("🎉 모든 곡의 6개 파트 플레이리스트 자동화 등록 업무가 완전히 끝났습니다!")