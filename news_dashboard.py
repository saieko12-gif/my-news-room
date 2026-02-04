import streamlit as st
import feedparser
import ssl
import urllib.parse
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

st.title("📰 B2B 영업 이슈 & 뉴스 모니터링")
st.markdown("버튼 하나로 키워드 자동 세팅! **스마트한 영업맨의 비밀무기**")

# ---------------------------------------------------------
# 3. 사이드바 설정 (여기가 핵심 업그레이드!)
# ---------------------------------------------------------
st.sidebar.header("🛠️ 검색 조건 설정")

# --- [기능 추가] 키워드 프리셋(Preset) 정의 ---
# 니가 원하던 '키워드 묶음'들이다. 입맛대로 수정해도 된다.
preset_hotel = "호텔 리모델링, 신규 호텔 오픈, 리조트 착공, 5성급 호텔 리뉴얼, 호텔 FF&E, 생활숙박시설 분양, 호텔 매각"
preset_office = "사옥 이전, 통합 사옥 건립, 스마트 오피스, 기업 연수원 건립, 공공청사 리모델링, 공유 오피스 출점, 오피스 인테리어"
preset_market = "건자재 가격, 친환경 자재, 모듈러 주택, 아파트 특판 가구, 한샘 B2B, LX하우시스, 현대건설 수주, GS건설 수주"
preset_all = f"{preset_hotel}, {preset_office}, {preset_market}" # 다 합친거

# --- [기능 추가] 세션 상태 초기화 ---
# 입력창에 들어갈 값을 기억하는 변수(storage)를 만든다.
if 'search_keywords' not in st.session_state:
    st.session_state['search_keywords'] = preset_hotel # 기본값은 호텔로 시작

# --- [기능 추가] 바로가기 버튼들 ---
st.sidebar.subheader("⚡ 키워드 자동 완성 (클릭해봐라)")

# 버튼을 2열로 예쁘게 배치
col1, col2 = st.sidebar.columns(2)

# 각 버튼을 누르면 -> 저장된 변수(search_keywords) 값을 바꾼다!
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

# --- 입력창 (여기서 key='search_keywords'가 핵심!) ---
# 위에서 버튼 누르면 바뀐 값이 여기에 자동으로 쏙 들어간다.
user_input = st.sidebar.text_area(
    "검색할 키워드 (직접 수정 가능)", 
    key='search_keywords', # 버튼이랑 연결된 고리
    height=150
)

# 콤마로 잘라서 리스트로 변환
keywords = [k.strip() for k in user_input.split(',') if k.strip()]

# 기간 필터링
period_option = st.sidebar.selectbox(
    "조회 기간",
    ["전체 보기", "최근 24시간", "최근 3일", "최근 1주일"]
)

st.sidebar.info(f"현재 **{len(keywords)}개** 키워드를 감시 중이데이!")

# ---------------------------------------------------------
# 4. 뉴스 가져오기 함수 (기존과 동일)
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

            all_news.append({
                'keyword': term,
                'title': entry.title,
                'link': entry.link,
                'published': pub_date,
                'source': entry.get('source', {}).get('title', 'Google News')
            })
            
    return all_news

# ---------------------------------------------------------
# 5. 메인 로직 실행
# ---------------------------------------------------------
if st.button("🔄 최신 뉴스 다시 불러오기"):
    st.cache_data.clear()

with st.spinner('뉴스 긁어오는 중... 잠만 기다리바라...'):
    news_list = get_news(keywords)

# 날짜순 정렬
news_list.sort(key=lambda x: x['published'], reverse=True)

# 기간 필터링 적용
filtered_news = []
if news_list:
    now = datetime.now(news_list[0]['published'].tzinfo) 

    for news in news_list:
        pub_date = news['published']
        
        if period_option == "최근 24시간":
            if (now - pub_date) > timedelta(hours=24): continue
        elif period_option == "최근 3일":
            if (now - pub_date) > timedelta(days=3): continue
        elif period_option == "최근 1주일":
            if (now - pub_date) > timedelta(days=7): continue
            
        filtered_news.append(news)

# 결과 보여주기
if not filtered_news:
    st.warning("조건에 맞는 뉴스가 없다! 키워드를 바꾸거나 기간을 늘려보래이.")
else:
    st.success(f"총 **{len(filtered_news)}개**의 뉴스를 찾았다!")
    
    for i, news in enumerate(filtered_news):
        date_str = news['published'].strftime("%Y-%m-%d %H:%M")
        
        with st.expander(f"[{news['keyword']}] {news['title']}"):
            st.write(f"**출처:** {news['source']} | **일시:** {date_str}")
            st.link_button("기사 원문 보러가기 👉", news['link'])
