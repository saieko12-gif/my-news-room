import streamlit as st
import feedparser
import ssl
import urllib.parse
import re
import pandas as pd
import plotly.express as px
import OpenDartReader # <--- [추가] DART 통신용
from datetime import datetime, timedelta
from dateutil import parser

# ---------------------------------------------------------
# 1. 설정 & 로고 & API 키 설정
# ---------------------------------------------------------
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

st.set_page_config(
    page_title="영업용 뉴스 & 공시 수집기",
    page_icon="💼",
    layout="wide"
)

# [중요] 니가 가져온 DART API 키
DART_API_KEY = "3522c934d5547db5cba3f51f8d832e1a82ebce55"

try:
    st.sidebar.image("logo.png", use_column_width=True)
except:
    pass

st.title("💼 B2B 영업 인텔리전스 (News & DART)")
st.markdown("뉴스 트렌드와 기업 공시를 한눈에! **스마트한 영업맨의 비밀무기**")

# ---------------------------------------------------------
# 2. 사이드바 (공통 설정)
# ---------------------------------------------------------
st.sidebar.header("🛠️ 검색 조건 설정")

# --- 탭 구분 (뉴스 vs 공시) ---
mode = st.sidebar.radio("모드 선택", ["📰 뉴스 모니터링", "🏢 기업 공시 검색"])

# ---------------------------------------------------------
# 3. 공통 함수들 (뉴스용)
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
# 4. 공통 함수들 (DART용)
# ---------------------------------------------------------
@st.cache_resource # DART 연결은 한 번만 하면 됨
def get_dart_system():
    try:
        dart = OpenDartReader(DART_API_KEY) 
        return dart
    except Exception as e:
        return None

# ---------------------------------------------------------
# [탭 1] 뉴스 모니터링 로직
# ---------------------------------------------------------
if mode == "📰 뉴스 모니터링":
    
    # 뉴스 전용 사이드바 메뉴
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
    
    st.sidebar.info(f"뉴스: **{len(keywords)}개** 키워드 감시 중")

    if st.button("🔄 최신 뉴스 다시 불러오기"):
        st.cache_data.clear()

    with st.spinner('뉴스 데이터 분석 중...'):
        news_list = get_news(keywords)

    news_list.sort(key=lambda x: x['published'], reverse=True)

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
        st.subheader("📊 키워드별 이슈 트렌드")
        df = pd.DataFrame(date_filtered_news)
        if not df.empty:
            keyword_counts = df['keyword'].value_counts().reset_index()
            keyword_counts.columns = ['키워드', '뉴스 개수']
            fig_bar = px.bar(keyword_counts, x='뉴스 개수', y='키워드', orientation='h', text='뉴스 개수', color='뉴스 개수', color_continuous_scale='Teal', title="")
            fig_bar.update_layout(plot_bgcolor='rgba(0,0,0,0)', xaxis_title="", yaxis_title="", height=250, margin=dict(l=0, r=0, t=30, b=0))
            fig_bar.update_yaxes(categoryorder='total ascending')
            st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()
        st.subheader(f"🔎 뉴스 상세 검색 (총 {len(date_filtered_news)}건)")
        col_filter1, col_filter2 = st.columns([1, 2])
        with col_filter1: search_query = st.text_input("텍스트 검색", placeholder="제목 검색...")
        found_keywords = list(set([n['keyword'] for n in date_filtered_news]))
        with col_filter2: selected_keywords = st.multiselect("키워드 선택", options=found_keywords, default=found_keywords)
        
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
                if news['summary']: st.caption("📝 미리보기:"); st.info(news['summary'])
                st.write(f"**출처:** {news['source']} | **일시:** {full_date}")
                st.link_button("기사 원문 보러가기 👉", news['link'])

# ---------------------------------------------------------
# [탭 2] 기업 공시 검색 로직 (여기가 새로 추가됨!)
# ---------------------------------------------------------
elif mode == "🏢 기업 공시 검색":
    st.sidebar.info("💡 회사 이름을 정확히 입력해야 뜬데이!")
    
    st.subheader("🏢 DART 기업 공시 검색")
    st.markdown("다운로드 없이 **원문 바로보기** 가능! 경쟁사 동향 파악해라.")
    
    # 입력창
    col_d1, col_d2 = st.columns([3, 1])
    with col_d1:
        target_corp = st.text_input("회사 이름 입력 (예: 현대건설, GS리테일)", placeholder="회사명 입력 후 엔터...")
    with col_d2:
        # 최근 3개월 or 6개월 선택
        dart_period = st.selectbox("조회 기간", ["최근 3개월", "최근 6개월", "최근 1년"])
    
    if target_corp:
        dart = get_dart_system()
        
        if dart is None:
            st.error("DART 연결 실패! API 키를 확인하거나 requirements.txt에 'opendartreader' 추가했는지 봐라.")
        else:
            with st.spinner(f"'{target_corp}' 공시 자료 뒤지는 중... (처음엔 좀 걸린데이)"):
                try:
                    # 날짜 계산
                    end_date = datetime.now()
                    if dart_period == "최근 3개월": start_date = end_date - timedelta(days=90)
                    elif dart_period == "최근 6개월": start_date = end_date - timedelta(days=180)
                    else: start_date = end_date - timedelta(days=365)
                    
                    # DART에서 리스트 가져오기
                    # (회사이름, 시작일, 종료일, 보고서유형=수시공시 등)
                    reports = dart.list(target_corp, start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
                    
                    if reports is None or reports.empty:
                        st.warning(f"'{target_corp}'에 대한 공시가 없거나, 회사 이름을 못 찾겠다. 정확하게 쳤나?")
                    else:
                        st.success(f"총 **{len(reports)}건**의 공시를 찾았다!")
                        
                        # 표 보여주기 좋게 정리
                        for index, row in reports.iterrows():
                            # 중요 공시는 빨간색으로 강조하면 좋다
                            title = row['report_nm']
                            rcept_no = row['rcept_no']
                            corp_name = row['corp_name']
                            date_str = row['rcept_dt'] # YYYYMMDD
                            
                            # 날짜 예쁘게 (20240206 -> 2024-02-06)
                            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                            
                            # [핵심] DART 뷰어 링크 생성
                            dart_url = f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
                            
                            # 카드 형태로 출력
                            with st.container():
                                col_r1, col_r2 = st.columns([4, 1])
                                with col_r1:
                                    st.markdown(f"**[{formatted_date}] {title}**")
                                    st.caption(f"회사: {corp_name} | 제출인: {row['flr_nm']}")
                                with col_r2:
                                    st.link_button("📄 원문 보기", dart_url)
                                st.divider()
                                
                except Exception as e:
                    # 회사 이름이 틀렸거나 시스템 에러일 때
                    st.error(f"에러 났다! 회사 이름을 정확하게 입력했나 확인해봐라. (에러내용: {e})")
