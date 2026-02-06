import streamlit as st
import feedparser
import ssl
import urllib.parse
import re
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dateutil import parser

# ---------------------------------------------------------
# 1. 설정 & 로고
# ---------------------------------------------------------
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

st.set_page_config(
    page_title="영업용 뉴스 수집기",
    page_icon="📰",
    layout="wide"
)

try:
    st.sidebar.image("logo.png", use_column_width=True)
except:
    pass

st.title("📰 B2B 영업 이슈 & 뉴스 모니터링")
st.markdown("데이터로 보는 영업 트렌드! **스마트한 영업맨의 비밀무기**")

# ---------------------------------------------------------
# 2. 사이드바
# ---------------------------------------------------------
st.sidebar.header("🛠️ 검색 조건 설정")

preset_hotel = "호텔 리모델링, 신규 호텔 오픈, 리조트 착공, 5성급 호텔 리뉴얼, 호텔 FF&E, 생활숙박시설 분양, 호텔 매각, 샌즈"
preset_office = "사옥 이전, 통합 사옥 건립, 스마트 오피스, 기업 연수원 건립, 공공청사 리모델링, 공유 오피스 출점, 오피스 인테리어, 데이터센터"
preset_market = "건자재 가격, 친환경 자재, 모듈러 주택, 현대건설 수주, GS건설 수주, 디엘건설, 디엘이앤씨, 현대엔지니어링"
preset_all = f"{preset_hotel}, {preset_office}, {preset_market}"

if 'search_keywords' not in st.session_state:
    st.session_state['search_keywords'] = preset_hotel

st.sidebar.subheader("⚡ 키워드 자동 완성")
col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("🏨 호텔/리조트"): st.session_state['search_keywords'] = preset_hotel
    if st.button("🏗️ 건자재/동향"): st.session_state['search_keywords'] = preset_market
with col2:
    if st.button("🏢 오피스/사옥"): st.session_state['search_keywords'] = preset_office
    if st.button("🔥 영업 풀세트"): st.session_state['search_keywords'] = preset_all

user_input = st.sidebar.text_area("검색할 키워드", key='search_keywords', height=150)
keywords = [k.strip() for k in user_input.split(',') if k.strip()]

period_option = st.sidebar.selectbox("조회 기간", ["전체 보기", "최근 24시간", "최근 3일", "최근 1주일", "최근 1개월"])

st.sidebar.info(f"현재 **{len(keywords)}개** 키워드를 감시 중이데이!")

# ---------------------------------------------------------
# 3. 함수들
# ---------------------------------------------------------
def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext[:150] + "..." 

@st.cache_data(ttl=600)
def get_news(search_terms):
    all_news = []
    for term in search_terms:
        encoded_term = urllib.parse.quote(term)
        url = f"https://news.google.com/rss/search?q={encoded_term}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        for entry in feed.entries:
            try: pub_date = parser.parse(entry.published)
            except: pub_date = datetime.now()
            
            clean_summary = clean_html(entry.get('description', ''))
            
            all_news.append({
                'keyword': term,
                'title': entry.title,
                'link': entry.link,
                'published': pub_date,
                'summary': clean_summary,
                'source': entry.get('source', {}).get('title', 'Google News')
            })
    return all_news

# ---------------------------------------------------------
# 4. 메인 실행
# ---------------------------------------------------------
if st.button("🔄 최신 뉴스 다시 불러오기"):
    st.cache_data.clear()

with st.spinner('데이터 분석 중...'):
    news_list = get_news(keywords)

news_list.sort(key=lambda x: x['published'], reverse=True)

# 1차 필터링
date_filtered_news = []
if news_list:
    now = datetime.now(news_list[0]['published'].tzinfo) 
    for news in news_list:
        pub_date = news['published']
        if period_option == "최근 24시간" and (now - pub_date) > timedelta(hours=24): continue
        elif period_option == "최근 3일" and (now - pub_date) > timedelta(days=3): continue
        elif period_option == "최근 1주일" and (now - pub_date) > timedelta(days=7): continue
        elif period_option == "최근 1개월" and (now - pub_date) > timedelta(days=30): continue
        date_filtered_news.append(news)

if not date_filtered_news:
    st.warning("조건에 맞는 뉴스가 없다!")
else:
    st.divider()
    
    # ==========================================
    # [수정됨] 도넛 차트 빼고 막대만 꽉 채움!
    # ==========================================
    st.subheader("📊 키워드별 이슈 트렌드")
    
    df = pd.DataFrame(date_filtered_news)
    
    if not df.empty:
        keyword_counts = df['keyword'].value_counts().reset_index()
        keyword_counts.columns = ['키워드', '뉴스 개수']
        
        # 가로 막대 차트 (이제 화면 꽉 차게 나옴)
        fig_bar = px.bar(
            keyword_counts, 
            x='뉴스 개수', 
            y='키워드', 
            orientation='h', 
            text='뉴스 개수', 
            color='뉴스 개수', 
            color_continuous_scale='Teal', 
            title="" # 제목은 위 subheader가 있으니 생략
        )
        
        # 디자인 다듬기 (깔끔하게)
        fig_bar.update_layout(
            plot_bgcolor='rgba(0,0,0,0)', 
            xaxis_title="", 
            yaxis_title="",
            height=250, # 높이 적당히
            margin=dict(l=0, r=0, t=20, b=0) # 여백 조절
        )
        
        # 순서 정렬 (뉴스 많은 순서대로 위로 가게)
        fig_bar.update_yaxes(categoryorder='total ascending')
        
        st.plotly_chart(fig_bar, use_container_width=True)

    # ==========================================
    
    st.divider()
    
    # 리스트 필터링
    st.subheader(f"🔎 뉴스 상세 검색 (총 {len(date_filtered_news)}건)")
    col_filter1, col_filter2 = st.columns([1, 2])
    
    with col_filter1:
        search_query = st.text_input("텍스트 검색", placeholder="제목 검색...")
    
    found_keywords = list(set([n['keyword'] for n in date_filtered_news]))
    with col_filter2:
        selected_keywords = st.multiselect(
            "보고 싶은 키워드만 선택",
            options=found_keywords,
            default=found_keywords
        )
    
    final_news = []
    for news in date_filtered_news:
        if news['keyword'] not in selected_keywords: continue
        if search_query and (search_query not in news['title']): continue
        final_news.append(news)
    
    st.success(f"필터 적용 후: **{len(final_news)}개** 뉴스 표시 중")
    
    for news in final_news:
        short_date = news['published'].strftime("%m/%d")
        full_date = news['published'].strftime("%Y-%m-%d %H:%M")
        
        with st.expander(f"({short_date}) [{news['keyword']}] {news['title']}"):
            if news['summary']:
                st.caption("📝 미리보기:")
                st.info(news['summary'])
            
            st.write(f"**출처:** {news['source']} | **일시:** {full_date}")
            st.link_button("기사 원문 보러가기 👉", news['link'])

    if len(final_news) == 0:
        st.info("조건에 맞는 기사가 없다.")

