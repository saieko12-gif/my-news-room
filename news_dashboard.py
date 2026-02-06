import streamlit as st
import feedparser
import ssl
import urllib.parse
import re
import pandas as pd
import plotly.express as px
import OpenDartReader
from datetime import datetime, timedelta
from dateutil import parser

# ---------------------------------------------------------
# 1. 설정 & 로고 & API 키
# ---------------------------------------------------------
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

st.set_page_config(
    page_title="영업용 뉴스 & 공시 수집기",
    page_icon="💼",
    layout="wide"
)

# [중요] 니 API 키
DART_API_KEY = "3522c934d5547db5cba3f51f8d832e1a82ebce55"

try:
    st.sidebar.image("logo.png", use_column_width=True)
except:
    pass

st.title("💼 B2B 영업 인텔리전스 (News & DART)")
st.markdown("뉴스 트렌드와 기업 공시를 한눈에! **스마트한 영업맨의 비밀무기**")

# ---------------------------------------------------------
# 2. 사이드바 (모드 선택)
# ---------------------------------------------------------
st.sidebar.header("🛠️ 검색 조건 설정")
mode = st.sidebar.radio("모드 선택", ["📰 뉴스 모니터링", "🏢 기업 공시 검색"])

# ---------------------------------------------------------
# 3. 공통 함수 (뉴스 & DART)
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

# [수정] DART 시스템 로딩 (회사 목록까지 싹 가져옴)
@st.cache_resource
def get_dart_system():
    try:
        dart = OpenDartReader(DART_API_KEY) 
        # 처음 한 번 회사 목록(corp_codes)을 로딩해둔다 (약간 걸림)
        return dart
    except Exception as e:
        return None

# ---------------------------------------------------------
# [탭 1] 뉴스 모니터링
# ---------------------------------------------------------
if mode == "📰 뉴스 모니터링":
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
# [탭 2] 기업 공시 검색 (자동완성 기능 추가!)
# ---------------------------------------------------------
elif mode == "🏢 기업 공시 검색":
    
    st.subheader("🏢 DART 기업 공시 검색")
    st.markdown("회사 이름 일부만 입력해도 다 찾아준데이! (예: **'현대'**만 쳐봐라)")
    
    # 1. DART 시스템 연결 (최초 1회만 로딩)
    dart = get_dart_system()
    
    if dart is None:
        st.error("DART 연결 실패! API 키 확인해라.")
    else:
        # 2. 회사 검색창 (검색어 입력)
        search_text = st.text_input("회사명 검색", placeholder="여기에 '현대' 또는 '삼성' 쳐봐라...")
        
        target_corp = None # 최종 선택된 회사 이름
        
        # 3. 자동완성 로직
        if search_text:
            # 전체 회사 목록에서 검색어가 포함된 놈들만 필터링
            # dart.corp_codes에는 대한민국 모든 기업 리스트가 들어있다.
            corp_list = dart.corp_codes
            
            # 검색어가 이름에 포함된 회사 찾기 (contain)
            candidates = corp_list[corp_list['corp_name'].str.contains(search_text)]
            
            if candidates.empty:
                st.warning(f"'{search_text}'(으)로 검색된 회사가 없다. 다시 쳐봐라.")
            else:
                # 검색된 회사 리스트를 선택 상자(Selectbox)에 넣기
                # 사용자가 여기서 하나를 딱 고르면 그게 target_corp가 된다.
                target_corp = st.selectbox(
                    f"검색 결과 ({len(candidates)}개 찾음) - 하나 골라라", 
                    candidates['corp_name'].tolist()
                )
        
        st.divider()

        # 4. 공시 조회 (회사가 선택되었을 때만 실행)
        if target_corp:
            # 조회 기간 선택
            col_d1, col_d2 = st.columns([3, 1])
            with col_d1:
                st.info(f"📢 **'{target_corp}'** 공시를 조회한다!")
            with col_d2:
                dart_period = st.selectbox("조회 기간", ["최근 3개월", "최근 6개월", "최근 1년"])

            # 버튼 누르면 조회 시작 (매번 로딩 방지)
            if st.button("🚀 공시 조회하기"):
                with st.spinner(f"'{target_corp}' 자료 긁어오는 중..."):
                    try:
                        end_date = datetime.now()
                        if dart_period == "최근 3개월": start_date = end_date - timedelta(days=90)
                        elif dart_period == "최근 6개월": start_date = end_date - timedelta(days=180)
                        else: start_date = end_date - timedelta(days=365)
                        
                        reports = dart.list(target_corp, start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
                        
                        if reports is None or reports.empty:
                            st.warning("기간 내에 올라온 공시가 없다. 조용한 회사네.")
                        else:
                            st.success(f"총 **{len(reports)}건** 발견!")
                            
                            for index, row in reports.iterrows():
                                title = row['report_nm']
                                rcept_no = row['rcept_no']
                                corp_name = row['corp_name']
                                date_str = row['rcept_dt']
                                formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                                dart_url = f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
                                
                                with st.container():
                                    col_r1, col_r2 = st.columns([4, 1])
                                    with col_r1:
                                        st.markdown(f"**[{formatted_date}] {title}**")
                                        st.caption(f"제출인: {row['flr_nm']}")
                                    with col_r2:
                                        st.link_button("📄 원문 보기", dart_url)
                                    st.divider()
                    except Exception as e:
                        st.error(f"에러 났다: {e}")
