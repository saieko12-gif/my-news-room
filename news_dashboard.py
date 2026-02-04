import streamlit as st
import feedparser
import ssl
from datetime import datetime, timedelta
from dateutil import parser # 날짜 계산용

# ---------------------------------------------------------
# 1. 회사 보안망(SSL) 우회 설정 (필수!)
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
st.markdown("현대리바트 영업맨을 위한 **실시간 뉴스 자동 수집기** (Feat. 보안 뚫음)")

# ---------------------------------------------------------
# 3. 사이드바 설정 (여기가 니가 찾던 부분!)
# ---------------------------------------------------------
st.sidebar.header("🛠️ 검색 조건 설정")

# (1) 키워드 입력창 (니가 원하던 기능!)
default_keywords = "호텔 리모델링, 건자재 가격, 건설업 전망, 현대리바트, 한샘 B2B, 신규 리조트"
user_input = st.sidebar.text_area(
    "검색할 키워드 (콤마 , 로 구분)", 
    value=default_keywords,
    height=100
)
# 콤마로 잘라서 리스트로 변환
keywords = [k.strip() for k in user_input.split(',') if k.strip()]

# (2) 기간 필터링
period_option = st.sidebar.selectbox(
    "조회 기간",
    ["전체 보기", "최근 24시간", "최근 3일", "최근 1주일"]
)

st.sidebar.info(f"현재 **{len(keywords)}개** 키워드를 감시 중이데이!")

# ---------------------------------------------------------
# 4. 뉴스 가져오기 함수
# ---------------------------------------------------------
@st.cache_data(ttl=600) # 10분마다 갱신
def get_news(search_terms):
    all_news = []
    
    for term in search_terms:
        # 구글 뉴스 RSS 주소
        url = f"https://news.google.com/rss/search?q={term}&hl=ko&gl=KR&ceid=KR:ko"
        
        # 데이터 가져오기
        feed = feedparser.parse(url)
        
        for entry in feed.entries:
            # 날짜 변환 (영어 -> 날짜객체)
            try:
                pub_date = parser.parse(entry.published)
            except:
                pub_date = datetime.now() # 에러나면 현재시간

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

# 날짜순 정렬 (최신순)
news_list.sort(key=lambda x: x['published'], reverse=True)

# 기간 필터링 적용
filtered_news = []
now = datetime.now(news_list[0]['published'].tzinfo) # 타임존 맞추기

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
        # 날짜 예쁘게 표시
        date_str = news['published'].strftime("%Y-%m-%d %H:%M")
        
        with st.expander(f"[{news['keyword']}] {news['title']}"):
            st.write(f"**출처:** {news['source']} | **일시:** {date_str}")
            st.link_button("기사 원문 보러가기 👉", news['link'])
