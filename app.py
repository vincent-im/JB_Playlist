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
st.title("🤖 2단계 링크 추출형 유튜브 플레이리스트 자동화 에이전트")
st.caption("유튜브 ID: vincent.jbim@gmail.com")

if "playlist_items" not in st.session_state:
    st.session_state.playlist_items = []

# 6개 파트별 매핑 정보 (키워드 매칭용 및 타겟 플레이리스트 명칭)
PART_MAPPING = {
    "합창": "Test(합창)",
    "소프": "Test(S)",
    "알토": "Test(A)",
    "테너": "Test(T)",
    "베이스": "Test(B)",
    "반주": "Test(반주)"
}

# ------------------------------------------------------------------
# 2. 🔍 [🚨 핵심 개편] 하위 페이지까지 추적하는 2단계 자동 추출 함수
# ------------------------------------------------------------------
def deep_extract_youtube_urls(main_html_url):
    """
    1단계: 메인 HTML에서 6개 파트 버튼(하위 링크)을 찾습니다.
    2단계: 각 하위 링크로 이동하여 진짜 유튜브 영상 주소를 추출합니다.
    """
    final_result = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        # --- 1단계: 메인 HTML 페이지 분석 ---
        st.text("🔍 1단계: 메인 HTML 페이지 접속 및 파트별 버튼 링크 수집 중...")
        response = requests.get(main_html_url, headers=headers, timeout=10)
        if response.status_code != 200:
            st.error(f"❌ 메인 페이지 로드 실패 (에러 코드: {response.status_code})")
            return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 메인 페이지 안의 모든 a 태그(링크) 추출
        links = soup.find_all('a')
        
        # 파트별 하위 페이지 URL을 저장할 임시 딕셔너리
        sub_page_urls = {}
        
        # 버튼 텍스트나 href 속성에 파트 키워드(합창, 소프 등)가 포함되어 있는지 검사
        for part_key in PART_MAPPING.keys():
            for link in links:
                link_text = link.get_text().strip()
                link_href = link.get('href', '')
                
                # 링크 텍스트나 주소에 '소프', '알토', '합창' 등의 글자가 들어가 있다면
                if part_key in link_text or part_key in link_href:
                    # 상대 경로 주소일 경우를 대비해 절대 경로로 자동 변환
                    absolute_url = urljoin(main_html_url, link_href)
                    sub_page_urls[part_key] = absolute_url
                    break
                    
        # 만약 키워드로 링크를 못 찾았다면, 하단 버튼 6개가 순서대로 배치되어 있다고 가정하고 순서대로 매핑 시도
        if len(sub_page_urls) < 6:
            st.warning("⚠️ 키워드 기반 링크 매칭 불완전: 하단 버튼 순서 배열 방식으로 재추출을 시도합니다.")
            valid_hrefs = [urljoin(main_html_url, l.get('href')) for l in links if l.get('href') and not l.get('href').startswith('#')]
            # 중복 제거 및 메인 페이지 주소 제외
            valid_hrefs = [u for u in list(dict.fromkeys(valid_hrefs)) if u != main_html_url]
            
            for i, part_key in enumerate(PART_MAPPING.keys()):
                if i < len(valid_hrefs) and part_key not in sub_page_urls:
                    sub_page_urls[part_key] = valid_hrefs[i]

        # --- 2단계: 각 파트별 하위 HTML 페이지 들어가서 유튜브 주소 따기 ---
        st.text("🔍 2단계: 수집된 6개 하위 파트 페이지로 이동하여 진짜 유튜브 주소 추출 중...")
        yt_pattern = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
        
        for part_key, playlist_name in PART_MAPPING.items():
            target_sub_url = sub_page_urls.get(part_key)
            
            if target_sub_url:
                try:
                    sub_response = requests.get(target_sub_url, headers=headers, timeout=7)
                    if sub_response.status_code == 200:
                        # 하위 페이지 HTML 소스코드에서 유튜브 11자리 ID 패턴 검색
                        found_ids = re.findall(yt_pattern, sub_response.text)
                        if found_ids:
                            # 가장 상단에 발견된 첫 번째 유튜브 영상을 진짜 주소로 확정
                            real_yt_url = f"https://www.youtube.com/watch?v={found_ids[0]}"
                            final_result[playlist_name] = real_yt_url
                        else:
                            final_result[playlist_name] = ""
                    else:
                        final_result[playlist_name] = ""
                except Exception:
                    final_result[playlist_name] = ""
            else:
                final_result[playlist_name] = ""
                
        return final_result

    except Exception as e:
        st.error(f"❌ 다단계 주소 자동 추출 중 치명적 에러 발생: {e}")
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
        body={"snippet": {"title": title, "description": "에이전트 2단계 자동 생성"}, "status": {"privacyStatus": "private"}}
    )
    return create_request.execute()["id"]

def add_video_to_playlist(youtube, playlist_id, video_id):
    request = youtube.playlistItems().insert(
        part="snippet",
        body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
    )
    return request.execute()

# ------------------------------------------------------------------
# 4. ➕ 새 곡 추가 UI
# ------------------------------------------------------------------
st.subheader("➕ 새 곡 추가하기")
with st.form(key="add_song_form", clear_on_submit=True):
    col1, col2 = st.columns([2, 3])
    with col1:
        new_title = st.text_input("곡 명칭 입력", placeholder="예: 시월의 어느 멋진 날에")
    with col2:
        new_url = st.text_input("메인 HTML Link 주소 입력 (하위에 6개 버튼이 있는 주소)", placeholder="http://domain.com/main_page.html")
    
    submit_button = st.form_submit_button(label="목록에 추가")
    if submit_button and new_title and new_url:
        new_id = max([item["id"] for item in st.session_state.playlist_items]) + 1 if st.session_state.playlist_items else 1
        st.session_state.playlist_items.append({"id": new_id, "title": new_title, "url": new_url})
        st.rerun()

st.divider()

# ------------------------------------------------------------------
# 5. 📋 현재 Playlist 등재 목록 및 순서 조정
# ------------------------------------------------------------------
st.subheader("📋 현재 Playlist 등재 목록 및 순서 조정")

if not st.session_state.playlist_items:
    st.warning("현재 등록된 곡이 없습니다. 위의 폼에서 곡을 먼저 추가해 주세요.")
else:
    display_list = [f"☰  {item['title']}  |  🌐 메인 HTML: {item['url']}" for item in st.session_state.playlist_items]
    sorted_display_list = sort_items(display_list)
    
    updated_items = []
    for display_text in sorted_display_list:
        clean_title = display_text.replace("☰  ", "").split("  |  🌐 메인 HTML:")[0]
        for item in st.session_state.playlist_items:
            if item["title"] == clean_title:
                updated_items.append(item)
                break
    st.session_state.playlist_items = updated_items

    for idx, item in enumerate(st.session_state.playlist_items):
        col_txt, col_btn = st.columns([5, 1])
        with col_txt:
            st.markdown(f"**{idx + 1}. {item['title']}** (메인 URL: {item['url']})")
        with col_btn:
            if st.button("➖ 삭제", key=f"del_{item['id']}_{idx}"):
                st.session_state.playlist_items.pop(idx)
                st.rerun()

    st.divider()

    # ------------------------------------------------------------------
    # 6. 🚀 하위 추적형 원클릭 자동화 실행 영역
    # ------------------------------------------------------------------
    st.subheader("⚙️ 플레이리스트 원클릭 자동 반영")
    st.info("✨ Playlist에 반영 버튼을 누르면 에이전트가 메인 HTML 하단 버튼들을 타고 들어가 6개의 유튜브 주소를 스스로 전부 수집해 옵니다.")
    
    if st.button("✨ Playlist에 반영 (이동 및 추출 100% 자동화)", type="primary", use_container_width=True):
        youtube = get_youtube_service()
        
        if youtube:
            for item in st.session_state.playlist_items:
                st.markdown(f"### 📂 곡명: **{item['title']}** 심층 데이터 분석 및 등록 시작")
                
                # 고도화된 다단계 자동 추출 함수 호출
                with st.status("🤖 에이전트가 하위 링크들을 클릭하여 유튜브 주소를 탐색 중...", expanded=True) as status:
                    extracted_part_urls = deep_extract_youtube_urls(item["url"])
                    status.update(label="🧬 파트별 원본 유튜브 주소 분석 완료!", state="complete")
                
                if extracted_part_urls:
                    # 완벽하게 수집된 6개 파트의 원본 유튜브 주소로 플레이리스트 적재 진행
                    for playlist_name, url in extracted_part_urls.items():
                        if url:
                            video_id = extract_video_id(url)
                            if video_id:
                                with st.spinner(f"'{playlist_name}'에 유튜브 영상 등록 중..."):
                                    p_id = get_or_create_playlist(youtube, playlist_name)
                                    add_video_to_playlist(youtube, p_id, video_id)
                                st.success(f"✅ [{playlist_name}] 하위 페이지에서 영상 추출 및 최종 등록 성공! ➡️ {url}")
                            else:
                                st.error(f"❌ {playlist_name}: 비디오 ID 파싱 실패")
                        else:
                            st.warning(f"⚠️ [{playlist_name}]: 연관 하위 웹페이지 내에서 유튜브 플레이어를 발견하지 못했습니다.")
                else:
                    st.error(f"❌ '{item['title']}'의 메인 웹페이지 구조 분석에 실패했습니다.")
            
            st.balloons()
            st.success("🎉 수동 이동 및 링크 복사 과정이 모두 생략되었습니다. 자동화 작업이 성공적으로 완료되었습니다!")