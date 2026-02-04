import streamlit as st
import feedparser
import ssl
import urllib.parse
import re # <--- [추가] HTML 태그 지우는 청소 도구
from datetime import datetime, timedelta
from dateutil import parser

# ---------------------------------------------------------
# 1. 회사 보안망(SSL) 우회 설정
# ---------------------------------------------------------
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

# ---------------------------------------------------------
# 2. 페이지 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="영업용 뉴스 수집기",
    page_icon="📰",
    layout="wide"
)

# 사이드바 로고 (있으면 뜨고 없으면 무시)
try:
    st.sidebar.image("logo.png", use_column_width=True)
except:
    pass

st.title("📰 B2B 영업 이슈 & 뉴스 모니터링")
st.markdown("버튼 하나로 키워드 자동 세팅! **스마트한 영업맨의 비밀무기**")

# ---------------------------------------------------------
# 3. 사이드바 설정
# ---------------------------------------------------------
st.sidebar.header("🛠️ 검색 조건 설정")

# --- 키워드 프리셋 ---
preset_hotel = "호텔 리모델링, 신규 호텔 오픈, 리조트 착공, 5성급 호텔 리뉴얼, 호텔 FF&E, 생활숙박시설 분양, 호텔 매각"
preset_office = "사옥 이전, 통합 사옥 건립, 스마트 오피스, 기업 연수원 건립, 공공청사 리모델링, 공유 오피스 출점, 오피스 인테리어"
preset_market = "건자재 가격, 친환경 자재, 모듈러 주택, 아파트 특판 가구, 한샘 B2B, LX하우시스, 현대건설 수주, GS건설 수주"
preset_all = f"{preset_hotel}, {preset_office}, {preset_market}"

# --- 세션 상태 초기화 ---
if 'search_keywords' not in st.session_state:
    st.session_state['search_keywords'] = preset_hotel

# --- 바로가기 버튼들 ---
st.sidebar.subheader("⚡ 키워드 자동 완성")
col1, col2 = st.sidebar.columns(2)

with col1:
    if st.button("🏨 호텔/리조트"):
        st.session_state['search_keywords'] = preset_hotel
    if st.button("🏗️ 건자재/동향"):
        st.session_state['search_keywords'] = preset_market
        
with col2:
    if st.button("🏢 오피스/사옥"):
        st.session_state['search_keywords'] = preset_office
    if st.button("🔥 영업 풀세트"):
        st.session_state['search_keywords'] = preset_all

# --- 입력창 ---
user_input = st.sidebar.text_area(
    "검색할 키워드 (직접 수정 가능)", 
    key='search_keywords', 
    height=150
)

keywords = [k.strip() for k in user_input.split(',') if k.strip()]

# --- 기간 필터링 ---
period_option = st.sidebar.selectbox(
    "조회 기간",
    ["전체 보기", "최근 24시간", "최근 3일", "최근 1주일", "최근 1개월"]
)

st.sidebar.info(f"현재 **{len(keywords)}개** 키워드를 감시 중이데이!")

# ---------------------------------------------------------
# [기능 추가] HTML 태그 청소 함수 (지저분한거 닦아내기)
# ---------------------------------------------------------
def clean_html(raw_html):
    # <...> 처럼 생긴 태그들을 찾아서 없애버린다
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext

# ---------------------------------------------------------
# 4. 뉴스 가져오기 함수
# ---------------------------------------------------------
@st.cache_data(ttl=600)
def get_news(search_terms):
    all_news = []
    
    for term in search_terms:
        encoded_term = urllib.parse.quote(term)
        url = f"https://news.google.com/rss/search?q={encoded_term}&hl=ko&gl=KR&ceid=KR:ko"
        
        feed = feedparser.parse(url)
        
        for entry in feed.entries:
            try:
                pub_date = parser.parse(entry.published)
            except:
                pub_date = datetime.now()

            # [수정] 요약문(description) 가져와서 청소하기
            raw_summary = entry.get('description', '')
            clean_summary = clean_html(raw_summary)

            all_news.append({
                'keyword': term,
                'title': entry.title,
                'link': entry.link,
                'published': pub_date,
                'summary': clean_summary, # <---
