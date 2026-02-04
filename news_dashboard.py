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

# 1차 필터링: 날짜(기간) 기준
date_filtered_news = []
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
        elif period_option == "최근 1개월":
            if (now - pub_date) > timedelta(days=30): continue
            
        date_filtered_news.append(news)

# 결과가 있을 때만 2차 필터링(검색 & 키워드 선택) UI 표시
if not date_filtered_news:
    st.warning("조건에 맞는 뉴스가 없다! 기간을 좀 늘려보래이.")
else:
    st.divider() # 구분선
    
    # --- [기능 추가] 결과 내 재검색 및 필터링 UI ---
    st.subheader(f"🔎 검색된 뉴스 총 {len(date_filtered_news)}건 분석")
    
    col_filter1, col_filter2 = st.columns([1, 2])
    
    # 1. 결과 내 텍스트 검색
    with col_filter1:
        search_query = st.text_input("텍스트 검색 (제목)", placeholder="예: 삼성, 매각...")
    
    # 2. 키워드별 보기 선택 (체크박스 대신 멀티셀렉트가 훨씬 깔끔함!)
    # 검색된 뉴스에 포함된 키워드 목록만 추출
    found_keywords = list(set([n['keyword'] for n in date_filtered_news]))
    with col_filter2:
        selected_keywords = st.multiselect(
            "보고 싶은 키워드만 선택 (기본: 전체 선택)",
            options=found_keywords,
            default=found_keywords # 기본값은 다 보여주기
        )
    
    # --- 3. 최종 필터링 적용 ---
    final_news = []
    for news in date_filtered_news:
        # (1) 키워드 필터: 선택된 키워드에 포함되는가?
        if news['keyword'] not in selected_keywords:
            continue
        
        # (2) 텍스트 검색: 검색어가 제목에 있는가? (검색어 없으면 통과)
        if search_query and (search_query not in news['title']):
            continue
            
        final_news.append(news)
    
    # --- 4. 최종 결과 출력 ---
    st.success(f"필터 적용 후: **{len(final_news)}개** 뉴스 표시 중")
    
    for news in final_news:
        date_str = news['published'].strftime("%Y-%m-%d %H:%M")
        
        with st.expander(f"[{news['keyword']}] {news['title']}"):
            st.write(f"**출처:** {news['source']} | **일시:** {date_str}")
            st.link_button("기사 원문 보러가기 👉", news['link'])

    if len(final_news) == 0:
        st.info("필터링 조건에 맞는 기사가 없다. 조건을 좀 풀어바라!")
