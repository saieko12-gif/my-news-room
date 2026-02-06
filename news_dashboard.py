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
st.markdown("뉴스, 공시, 그리고 **최신 재무제표**까지 완벽하게! **스마트한 영업맨의 비밀무기**")

# ---------------------------------------------------------
# 2. 사이드바 (모드 선택)
# ---------------------------------------------------------
st.sidebar.header("🛠️ 검색 조건 설정")
mode = st.sidebar.radio("모드 선택", ["📰 뉴스 모니터링", "🏢 기업 공시 & 재무제표"])

# ---------------------------------------------------------
# 3. 공통 함수
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

@st.cache_resource
def get_dart_system():
    try:
        dart = OpenDartReader(DART_API_KEY) 
        return dart
    except Exception as e:
        return None

# [핵심 수정] 재무제표 샅샅이 뒤지는 함수
def get_financial_summary(dart, corp_name):
    # 2026년 초니까 2025년 데이터가 있으면 가져오고, 없으면 2024년 가져옴
    years = [2025, 2024]
    
    # 보고서 우선순위: 사업보고서(1년) -> 3분기 -> 반기 -> 1분기
    # 11011: 1년 전체 (가장 정확)
    # 11014: 3분기 (9월까지)
    # 11012: 반기 (6월까지)
    # 11013: 1분기 (3월까지)
    report_codes = [
        ('11011', '1년(사업보고서)'), 
        ('11014', '3분기 누적'), 
        ('11012', '반기 누적'), 
        ('11013', '1분기')
    ]
    
    for year in years:
        for code, code_name in report_codes:
            try:
                # 데이터 요청
                fs = dart.finstate(corp_name, year, reprt_code=code)
                
                if fs is not None and not fs.empty:
                    # 연결재무제표(CFS) 우선, 없으면 별도(OFS)
                    target_fs = fs[fs['fs_div'] == 'CFS']
                    if target_fs.empty:
                        target_fs = fs[fs['fs_div'] == 'OFS']

                    # 값 추출 함수
                    def get_value(account_names):
                        for nm in account_names:
                            row = target_fs[target_fs['account_nm'] == nm]
                            if not row.empty:
                                val = row.iloc[0]['thstrm_amount']
                                # 값이 없거나 비어있으면 패스
                                if pd.isna(val) or val == '': continue
                                
                                try:
                                    # 억원 단위 변환 (문자열 콤마 제거 후 계산)
                                    amount = float(str(val).replace(',', ''))
                                    return "{:,} 억".format(int(amount / 100000000))
                                except:
                                    return val
                        return "-"

                    # 데이터가 유의미한지 확인 (매출액이 '-'가 아니어야 함)
                    sales = get_value(['매출액', '수익(매출액)'])
                    if sales == "-": continue # 데이터는 왔는데 빈 껍데기면 다음 보고서 찾기

                    summary = {
                        "기준년도": f"{year}년 {code_name}", # 예: 2025년 3분기 누적
                        "매출액": sales,
                        "영업이익": get_value(['영업이익', '영업이익(손실)']),
                        "당기순이익": get_value(['당기순이익', '당기순이익(손실)']),
                        "자산총계": get_value(['자산총계']),
                        "부채총계": get_value(['부채총계']),
                        "자본총계": get_value(['자본총계'])
                    }
                    return summary # 찾았으면 바로 리턴!

            except:
                continue # 에러나면 다음 코드 시도
            
    return None # 끝까지 못 찾으면 None

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
# [탭 2] 기업 공시 & 재무제표
# ---------------------------------------------------------
elif mode == "🏢 기업 공시 & 재무제표":
    
    st.subheader("🏢 기업 분석 (공시 + 재무제표)")
    st.markdown("회사 이름이나 종목코드를 넣으면 **최신 재무상태**까지 털어드림!")
    
    dart = get_dart_system()
    
    if dart is None:
        st.error("DART 연결 실패! API 키 확인해라.")
    else:
        # 검색창
        search_text = st.text_input("회사명 또는 종목코드", placeholder="예: 현대리바트, 삼성전자, 079430")
        
        final_corp_name = None 
        
        if search_text:
            if search_text.isdigit() and len(search_text) >= 6:
                final_corp_name = search_text 
                st.info(f"🔢 종목코드 **'{search_text}'**로 조회한다!")
            else:
                try:
                    corp_list = dart.corp_codes
                    candidates = corp_list[corp_list['corp_name'].str.contains(search_text)]
                    
                    if not candidates.empty:
                        selected_from_list = st.selectbox(
                            f"목록에서 찾음 ({len(candidates)}개)", 
                            candidates['corp_name'].tolist()
                        )
                        final_corp_name = selected_from_list
                    else:
                        st.warning(f"목록에는 '{search_text}'가 없다.")
                        if st.checkbox(f"✅ '{search_text}' 이름 그대로 강제 조회하기"):
                            final_corp_name = search_text
                except:
                    final_corp_name = search_text
        
        if final_corp_name:
            if st.button("🚀 분석 시작하기"):
                
                # --- [A] 재무제표 섹션 ---
                st.divider()
                st.subheader(f"💰 '{final_corp_name}' 최신 재무 요약 (단위: 억원)")
                
                with st.spinner("최신 재무제표(3분기/반기) 뒤지는 중..."):
                    summary = get_financial_summary(dart, final_corp_name)
                    
                    if summary:
                        col_f1, col_f2, col_f3 = st.columns(3)
                        with col_f1:
                            st.metric("매출액", summary['매출액'])
                            st.metric("자산총계", summary['자산총계'])
                        with col_f2:
                            st.metric("영업이익", summary['영업이익'])
                            st.metric("부채총계", summary['부채총계'])
                        with col_f3:
                            st.metric("당기순이익", summary['당기순이익'])
                            st.metric("자본총계", summary['자본총계'])
                        # 몇 년도 몇 분기 자료인지 명시해줌
                        st.caption(f"※ 기준: **{summary['기준년도']}** (연결/별도 재무제표 기준)")
                    else:
                        st.warning("⚠️ 재무제표 정보를 불러올 수 없다. (비상장사이거나 DART에 표준 데이터가 없음)")

                # --- [B] 공시 리스트 섹션 ---
                st.divider()
                st.subheader(f"📋 최근 공시 내역")
                
                with st.spinner("공시 서류함 뒤지는 중..."):
                    try:
                        end_date = datetime.now()
                        start_date = end_date - timedelta(days=365) # 최근 1년
                        
                        reports = dart.list(final_corp_name, start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
                        
                        if reports is None or reports.empty:
                            st.error("최근 1년치 공시가 없다.")
                        else:
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
                                        st.link_button("📄 원문", dart_url)
                                    st.divider()
                    except Exception as e:
                        st.error(f"공시 불러오다 에러 났다: {e}")
