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
st.markdown("뉴스, 공시, 그리고 **누적 실적 분석**까지! **스마트한 영업맨의 비밀무기**")

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

# [핵심 수정] 3개월치 말고 '누적' 데이터 우선 추출하도록 변경!
def get_financial_summary_advanced(dart, corp_name):
    # 2025년부터 역순으로 검색
    years = [2025, 2024]
    
    report_codes = [
        ('11011', '사업보고서 (1년 확정)'), 
        ('11014', '3분기보고서 (누적)'), 
        ('11012', '반기보고서 (누적)'), 
        ('11013', '1분기보고서')
    ]
    
    for year in years:
        for code, code_name in report_codes:
            try:
                fs = dart.finstate(corp_name, year, reprt_code=code)
                
                if fs is not None and not fs.empty:
                    target_fs = fs[fs['fs_div'] == 'CFS']
                    if target_fs.empty:
                        target_fs = fs[fs['fs_div'] == 'OFS']

                    # 값 추출 함수 (누적 우선 로직 적용)
                    def get_data_pair(account_names):
                        for nm in account_names:
                            row = target_fs[target_fs['account_nm'] == nm]
                            if not row.empty:
                                try:
                                    # [여기가 핵심!] thstrm_add_amount(당기누적)가 있으면 그거 쓰고, 없으면 thstrm_amount(당기) 씀
                                    # 분기 보고서의 경우: add_amount = 누적, amount = 3개월치
                                    
                                    # 1. 올해 값 (This Term)
                                    this_val_str = ""
                                    if 'thstrm_add_amount' in row.columns and not pd.isna(row.iloc[0]['thstrm_add_amount']) and row.iloc[0]['thstrm_add_amount'] != '':
                                        this_val_str = row.iloc[0]['thstrm_add_amount'] # 누적 우선
                                    else:
                                        this_val_str = row.iloc[0]['thstrm_amount'] # 없으면 그냥 당기

                                    # 2. 작년 값 (Former Term) - 비교용
                                    prev_val_str = ""
                                    if 'frmtrm_add_amount' in row.columns and not pd.isna(row.iloc[0]['frmtrm_add_amount']) and row.iloc[0]['frmtrm_add_amount'] != '':
                                        prev_val_str = row.iloc[0]['frmtrm_add_amount'] # 작년 누적
                                    else:
                                        prev_val_str = row.iloc[0]['frmtrm_amount'] # 작년 당기

                                    # 숫자 변환
                                    this_val = float(str(this_val_str).replace(',', ''))
                                    
                                    if pd.isna(prev_val_str) or prev_val_str == '':
                                        prev_val = 0
                                    else:
                                        prev_val = float(str(prev_val_str).replace(',', ''))

                                    # 억원 단위 표시
                                    this_view = "{:,} 억".format(int(this_val / 100000000))
                                    prev_view = "{:,} 억".format(int(prev_val / 100000000))
                                    
                                    # 성장률 계산
                                    if prev_val == 0:
                                        delta = None
                                    else:
                                        delta = ((this_val - prev_val) / prev_val) * 100
                                        delta = f"{delta:.1f}%" 

                                    return this_view, delta, prev_view 
                                except:
                                    continue
                        return "-", None, "-"

                    sales_now, sales_delta, sales_prev = get_data_pair(['매출액', '수익(매출액)'])
                    op_now, op_delta, op_prev = get_data_pair(['영업이익', '영업이익(손실)'])
                    net_now, net_delta, net_prev = get_data_pair(['당기순이익', '당기순이익(손실)'])
                    
                    if sales_now == "-": continue 

                    # 링크 찾기
                    rcept_no = ""
                    try:
                        start_dt = f"{year}-01-01"
                        end_dt = f"{year}-12-31" 
                        reports = dart.list(corp_name, start=start_dt, end=end_dt, kind='A')
                        
                        target_name_keyword = ""
                        if code == '11011': target_name_keyword = "사업보고서"
                        elif code == '11014': target_name_keyword = "분기보고서"
                        elif code == '11012': target_name_keyword = "반기보고서"
                        
                        for idx, row in reports.iterrows():
                            if target_name_keyword in row['report_nm']:
                                rcept_no = row['rcept_no']
                                break
                    except:
                        rcept_no = ""

                    summary = {
                        "title": f"{year}년 {code_name} (누적 실적)", # 제목도 '누적'으로 변경
                        "매출": (sales_now, sales_delta, sales_prev),
                        "영업이익": (op_now, op_delta, op_prev),
                        "순이익": (net_now, net_delta, net_prev),
                        "rcept_no": rcept_no 
                    }
                    return summary

            except:
                continue
            
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
# [탭 2] 기업 공시 & 재무제표
# ---------------------------------------------------------
elif mode == "🏢 기업 공시 & 재무제표":
    
    st.subheader("🏢 기업 분석 (공시 + 재무성장률)")
    st.markdown("전년 대비 **얼마나 성장했는지(누적 기준)** 한눈에 보여준데이!")
    
    dart = get_dart_system()
    
    if dart is None:
        st.error("DART 연결 실패! API 키 확인해라.")
    else:
        search_text = st.text_input("회사명 또는 종목코드", placeholder="예: 현대리바트, 079430")
        
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
                        selected_from_list = st.selectbox(f"목록에서 찾음 ({len(candidates)}개)", candidates['corp_name'].tolist())
                        final_corp_name = selected_from_list
                    else:
                        st.warning(f"목록에는 '{search_text}'가 없다.")
                        if st.checkbox(f"✅ '{search_text}' 이름 그대로 강제 조회하기"):
                            final_corp_name = search_text
                except:
                    final_corp_name = search_text
        
        if final_corp_name:
            if st.button("🚀 분석 시작하기"):
                
                # --- [A] 성장률 분석 섹션 ---
                st.divider()
                st.subheader(f"📈 '{final_corp_name}' 재무 성적표")
                
                with st.spinner("누적 실적(조 단위) 계산하는 중..."):
                    summary = get_financial_summary_advanced(dart, final_corp_name)
                    
                    if summary:
                        st.markdown(f"**📌 기준: {summary['title']}** (전년 동기 대비)")
                        
                        col_f1, col_f2, col_f3 = st.columns(3)
                        
                        s_now, s_delta, s_prev = summary['매출']
                        o_now, o_delta, o_prev = summary['영업이익']
                        n_now, n_delta, n_prev = summary['순이익']
                        
                        with col_f1:
                            st.metric("매출액 (누적)", s_now, s_delta)
                            st.caption(f"작년 누적: {s_prev}")
                        with col_f2:
                            st.metric("영업이익 (누적)", o_now, o_delta)
                            st.caption(f"작년 누적: {o_prev}")
                        with col_f3:
                            st.metric("당기순이익 (누적)", n_now, n_delta)
                            st.caption(f"작년 누적: {n_prev}")
                            
                        if s_delta and "-" not in s_delta: 
                            growth = float(s_delta.replace('%',''))
                            if growth > 10:
                                st.success("🚀 와! 누적 매출이 작년보다 10% 이상 뛰었네! 분위기 좋다.")
                            elif growth > 0:
                                st.info("🙂 작년보다 매출이 조금 늘었다. 선방했네.")
                            else:
                                st.error("📉 작년보다 매출이 줄었다. 회사 분위기 살벌하겠는데?")
                                
                        if summary['rcept_no']:
                            dart_link = f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={summary['rcept_no']}"
                            st.link_button("📄 이 데이터 뽑아온 [분기보고서 원문] 보러가기", dart_link)
                            
                    else:
                        st.warning("⚠️ 재무 정보를 불러올 수 없다.")

                # --- [B] 공시 리스트 ---
                st.divider()
                st.subheader(f"📋 최근 공시 내역")
                
                with st.spinner("공시 서류함 뒤지는 중..."):
                    try:
                        end_date = datetime.now()
                        start_date = end_date - timedelta(days=365)
                        reports = dart.list(final_corp_name, start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
                        
                        if reports is None or reports.empty:
                            st.error("최근 1년치 공시가 없다.")
                        else:
                            for index, row in reports.iterrows():
                                title = row['report_nm']
                                rcept_no = row['rcept_no']
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
                        st.error(f"에러: {e}")
