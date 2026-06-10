import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
from streamlit_sortables import sort_items
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ------------------------------------------------------------------
# 1. 초기 세션 상태 및 기본 설정
# ------------------------------------------------------------------
st.set_page_config(page_title="중앙성가 플레이리스트 자동화 에이전트", layout="wide")
st.header("🎼 중앙성가 맞춤형 유튜브 플레이리스트 자동화 에이전트")
st.caption("유튜브 ID: vincent.jbim@gmail.com")

if "playlist_items" not in st.session_state:
    st.session_state.playlist_items = []

if "songbooks" not in st.session_state:
    st.session_state.songbooks = {}

# 6개 파트의 명칭과 유튜브 타겟 플레이리스트 이름 매핑 규칙
PART_MAPPING = {
    "합창": "Test(합창)",
    "소프": "Test(S)",
    "알토": "Test(A)",
    "테너": "Test(T)",
    "베이스": "Test(B)",
    "반주": "Test(반주)"
}

# ------------------------------------------------------------------
# 2. 🔍 중앙성가 전용 크롤링 및 파싱 백엔드 엔진
# ------------------------------------------------------------------
def extract_songs_from_joongang(songbook_url):
    """
    중앙성가 악보집 메인 페이지에서 '번호. 곡명' 구조를 텍스트 전체에서 정밀 추출하고,
    번호 패턴(번호/pop1.html)을 기반으로 곡별 하위 메인 HTML 주소를 강제 빌드합니다.
    """
    songs_db = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(songbook_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        
        all_text_elements = soup.find_all(string=True)
        base_path = songbook_url.rsplit('/', 1)[0] + '/'
        
        for element in all_text_elements:
            clean_text = element.strip()
            
            # 정규식 매칭: "01. 나의 힘이 되신 주님", "31. 축도송" 형태 조사
            match = re.search(r'^(\d+)\.\s*(.+)$', clean_text)
            
            if match:
                song_num = match.group(1)   
                song_title = match.group(2) 
                full_display_name = f"{song_num}. {song_title}"
                
                # 중앙성가 표준 URL 규칙에 맞춰 하위 이동 팝업 링크 조립
                constructed_sub_url = f"{base_path}{song_num}/pop1.html"
                songs_db[full_display_name] = constructed_sub_url
                
        return songs_db
    except Exception as e:
        st.error(f"❌ 악보집 파싱 중 오류 발생: {e}")
        return None

def deep_extract_youtube_urls(main_html_url):
    """ 각 곡별 하위 페이지(pop1.html) 내부에서 6개 파트 버튼 뒤에 숨겨진 유튜브 링크를 찾아냅니다. """
    final_result = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(main_html_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
            
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a')
        sub_page_urls = {}
        
        # 1단계: 하위 페이지 내 '합창', '소프', '알토' 등 글자가 적힌 파트 버튼들의 하이퍼링크 수집
        for part_key in PART_MAPPING.keys():
            for link in links:
                link_text = link.get_text().strip()
                link_href = link.get('href', '')
                if part_key in link_text or part_key in link_href:
                    sub_page_urls[part_key] = urljoin(main_html_url, link_href)
                    break
                    
        # 만약 글자로 매칭이 완벽히 안 될 경우, 하단에 나란히 배치된 버튼 순서대로 강제 매핑(안전장치)
        if len(sub_page_urls) < 6:
            valid_hrefs = [urljoin(main_html_url, l.get('href')) for l in links if l.get('href') and not l.get('href').startswith('#')]
            valid_hrefs = [u for u in list(dict.fromkeys(valid_hrefs)) if u != main_html_url]
            for i, part_key in enumerate(PART_MAPPING.keys()):
                if i < len(valid_hrefs) and part_key not in sub_page_urls:
                    sub_page_urls[part_key] = valid_hrefs[i]

        # 2단계: 최종 식별된 파트별 소스코드에 원격 접속하여, 진짜 유튜브 영상 주소 파싱
        yt_pattern = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
        for part_key, playlist_name in PART_MAPPING.items():
            target_sub_url = sub_page_urls.get(part_key)
            if target_sub_url:
                try:
                    sub_res = requests.get(target_sub_url, headers=headers, timeout=5)
                    found_ids = re.findall(yt_pattern, sub_res.text) if sub_res.status_code == 200 else []
                    final_result[playlist_name] = f"https://www.youtube.com/watch?v={found_ids[0]}" if found_ids else ""
                except:
                    final_result[playlist_name] = ""
            else:
                final_result[playlist_name] = ""
        return final_result
    except:
        return None

# ------------------------------------------------------------------
# 3. 🛠️ 유튜브 Data API v3 연동 백엔드 함수 그룹
# ------------------------------------------------------------------
def get_youtube_service():
    try:
        creds = Credentials(token=None, refresh_token=st.secrets["google"]["refresh_token"],
                            token_uri="https://oauth2.googleapis.com/token",
                            client_id=st.secrets["google"]["client_id"], client_secret=st.secrets["google"]["client_secret"])
        return build('youtube', 'v3', credentials=creds)
    except: 
        return None

def extract_video_id(url):
    m = re.search(r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})', url)
    return m.group(1) if m else None

def get_or_create_playlist(youtube, title):
    r = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
    for item in r.get("items", []):
        if item["snippet"]["title"] == title: 
            return