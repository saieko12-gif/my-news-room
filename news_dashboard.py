import streamlit as st
import feedparser
import ssl
import urllib.parse
import re
import pandas as pd
import plotly.express as px
# OpenDartReader는 필요할 때만 로딩
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from dateutil import parser

# ---------------------------------------------------------
# 1. 설정 & 스타일
# ---------------------------------------------------------
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

st.set_page_config(
    page_title="영업용 통합 대시보드",
    page_icon="⚡",
    layout="wide"
)

st.markdown("""
    <style>
        .block-container { padding-top: 2rem; } 
        div[data-testid="column"] { padding: 0 !important; } 
        .stButton button { 
            height: auto !important; min-height: 2.5rem;
            font-size: 0.9rem !important; 
            white-space: normal !important;
        }
        .link-box {
            border: 1px solid #e0e0e0; padding: 10px; border-radius: 5px; margin-bottom: 5px;
        }
    </style>
""", unsafe_allow_html=True)

# [중요] API 키 (DART만 남김)
DART_API_KEY = "3522c934d5547db5cba3f51f8d832e1a82ebce55"

# ---------------------------------------------------------
# 2. 사이드바
# ---------------------------------------------------------
try: st.sidebar.image("logo.png", use_column_width=True)
except: pass

st.sidebar.header("🚀 모드 선택")
mode = st.sidebar.radio("", ["📰 뉴스 모니터링", "🏢 기업 공시 & 재무제표", "🏗️ 건설/부동산 통계 (속보)"])

# ---------------------------------------------------------
# 3. 함수 모음
# ---------------------------------------------------------
def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)[:150] + "..." 

@st.cache_data(ttl=7200) 
def get_news(search_terms):
    all_news = []
    for term in search_terms:
        encoded_term = urllib.parse.quote(term)
        url = f"https://news.google.com/rss/search?q={encoded_term}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        for entry in feed.entries:
            try: pub_date = parser.parse(entry.published)
            except: pub_date = datetime.now()
            all_news.append({
                'keyword': term, 'title': entry.title, 'link': entry.link,
                'published': pub_date, 'summary': clean_html(entry.get('description', '')),
                'source': entry.get('source', {}).get('title', 'Google News')
            })
    return all_news

@st.cache_resource
def get_dart_system():
    try:
        import OpenDartReader 
        dart = OpenDartReader(DART_API_KEY) 
        return dart
    except: return None

def get_stock_chart(code):
    try:
        df = fdr.DataReader(code, datetime.now()-timedelta(days=365), datetime.now())
        if df.empty: return None
        l = df['Close'].iloc[-1]; p = df['Close'].iloc[-2]; c = ((l-p)/p)*100
        clr = '#ff4b4b' if c>0 else '#4b4bff'
        fig = px.area(df, x=df.index, y='Close')
        fig.update_layout(xaxis_title="", yaxis_title="", height=300, margin=dict(t=30,b=0,l=0,r=0), showlegend=False)
        fig.update_traces(line_color=clr)
        return fig, l, c
    except: return None

def get_financial_summary_advanced(dart, corp_name):
    years = [2025, 2024]
    codes = [('11011','사업보고서'), ('11014','3분기'), ('11012','반기'), ('11013','1분기')]
    for year in years:
        for code, c_name in codes:
            try:
                fs = dart.finstate(corp_name, year, reprt_code=code)
                if fs is None or fs.empty: continue
                t_fs = fs[fs['fs_div']=='CFS']
                if t_fs.empty: t_fs = fs[fs['fs_div']=='OFS']
                def gv(nms):
                    for nm in nms:
                        r = t_fs[t_fs['account_nm']==nm]
                        if not r.empty:
                            try:
                                ts = r.iloc[0].get('thstrm_add_amount', r.iloc[0]['thstrm_amount'])
                                if pd.isna(ts) or ts=='': ts = r.iloc[0]['thstrm_amount']
                                tv = float(str(ts).replace(',',''))
                                return "{:,} 억".format(int(tv/100000000))
                            except: continue
                    return "-"
                sn = gv(['매출액', '수익(매출액)'])
                on = gv(['영업이익', '영업이익(손실)'])
                nn = gv(['당기순이익', '당기순이익(손실)'])
                if sn == "-": continue
                return {"title": f"{year}년 {c_name}", "매출":sn, "영업":on, "순익":nn}
            except: continue
    return None

# ---------------------------------------------------------
# [탭 1] 뉴스 모니터링
# ---------------------------------------------------------
if mode == "📰 뉴스 모니터링":
    st.title("💼 B2B 영업 인텔리전스")
    
    preset_hotel = "호텔 리모델링, 신규 호텔 오픈, 리조트 착공, 5성급 호텔 리뉴얼, 호텔 FF&E, 생활숙박시설 분양, 호텔 매각, 샌즈"
    preset_market = "건자재 가격, 친환경 자재, 모듈러 주택, 현대건설 수주, GS건설 수주, 디엘건설, 디엘이앤씨, 현대엔지니어링"
    preset_office = "사옥 이전, 통합 사옥 건립, 스마트 오피스, 기업 연수원 건립, 공공청사 리모델링, 공유 오피스 출점, 오피스 인테리어, 데이터센터"
    preset_trend = "건설산업연구원 전망, 대한건설협회 수주, 건축 착공 면적, 건설 수주액, 인테리어 시장 전망, 건축허가 면적, 주택 인허가 실적, 아파트 매매 거래량, 미분양 관리지역"
    preset_pf = "부동산 신탁 수주, 신탁계약 체결, 리츠 인가, PF 대출 보증, 시행사 시공사 선정, 대구 재개발 수주, 부동산 PF 조달, 브릿지론 본PF 전환"
    
    preset_all = f"{preset_hotel}, {preset_market}, {preset_office}, {preset_trend}, {preset_pf}"

    if 'search_keywords' not in st.session_state: st.session_state['search_keywords'] = preset_hotel
    st.sidebar.subheader("⚡ 키워드 자동 완성")
    
    c1, c2 = st.sidebar.columns(2)
    with c1:
        if st.button("🏨 호텔/리조트"): st.session_state['search_keywords'] = preset_hotel
        if st.button("🏗️ 건자재/수주"): st.session_state['search_keywords'] = preset_market
        if st.button("💰 PF/신탁/금융"): st.session_state['search_keywords'] = preset_pf
    with c2:
        if st.button("🏢 오피스/사옥"): st.session_state['search_keywords'] = preset_office
        if st.button("📈 건설경기 동향"): st.session_state['search_keywords'] = preset_trend
        if st.button("🔥 전체 풀세트"): st.session_state['search_keywords'] = preset_all
    
    user_input = st.sidebar.text_area("검색 키워드", key='search_keywords', height=100)
    keywords = [k.strip() for k in user_input.split(',') if k.strip()]
    
    period = st.sidebar.selectbox("기간", ["전체 보기", "최근 24시간", "최근 3일", "최근 1주일", "최근 1개월", "최근 3개월"])
    
    if st.button("🔄 뉴스 새로고침"): st.cache_data.clear()

    with st.spinner('뉴스 긁어오는 중...'):
        news = get_news(keywords)
    news.sort(key=lambda x: x['published'], reverse=True)
    
    final = []
    now = datetime.now(news[0]['published'].tzinfo) if news else datetime.now()
    for n in news:
        diff = now - n['published']
        if period == "최근 24시간" and diff > timedelta(hours=24): continue
        if period == "최근 3일" and diff > timedelta(days=3): continue
        if period == "최근 1주일" and diff > timedelta(days=7): continue
        if period == "최근 1개월" and diff > timedelta(days=30): continue
        if period == "최근 3개월" and diff > timedelta(days=90): continue
        final.append(n)

    if not final: st.warning("뉴스 없다.")
    else:
        st.divider()
        cnt = pd.DataFrame(final)['keyword'].value_counts().reset_index()
        cnt.columns=['키워드','개수']
        fig = px.bar(cnt, x='개수', y='키워드', orientation='h', text='개수', color='개수', color_continuous_scale='Teal')
        fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', xaxis_title="", yaxis_title="", height=250, margin=dict(t=0,b=0,l=0,r=0))
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        for n in final:
            with st.expander(f"({n['published'].strftime('%m/%d')}) [{n['keyword']}] {n['title']}"):
                st.info(n['summary'])
                st.link_button("원문 보기", n['link'])

# ---------------------------------------------------------
# [탭 2] 기업 공시 & 재무제표
# ---------------------------------------------------------
elif mode == "🏢 기업 공시 & 재무제표":
    st.title("🏢 기업 분석 (상장사 + 신탁사)")
    search_txt = st.text_input("회사명 또는 종목코드", placeholder="예: 한국토지신탁, 034830")
    
    if st.button("🚀 분석 시작"):
        with st.spinner("DART 시스템 접속 중..."):
            dart = get_dart_system()
        if dart:
            try:
                final_corp = None; stock_code = None
                if search_txt.isdigit() and len(search_txt) >= 6:
                    final_corp = search_txt; stock_code = search_txt
                else:
                    cdf = dart.corp_codes
                    cands = cdf[cdf['corp_name'].str.contains(search_txt)]
                    if not cands.empty:
                        final_corp = cands.iloc[0]['corp_code']
                        stock_code = cands.iloc[0]['stock_code'] if cands.iloc[0]['stock_code'] else None
                    else: final_corp = search_txt

                st.divider(); st.subheader(f"📊 {search_txt} 분석 결과")
                if stock_code:
                    res = get_stock_chart(stock_code)
                    if res:
                        f, l, c = res; st.metric("현재가", f"{l:,}원", f"{c:.2f}%"); st.plotly_chart(f, use_container_width=True)
                
                sm = get_financial_summary_advanced(dart, final_corp)
                if sm:
                    c1,c2,c3=st.columns(3); c1.metric("매출",sm['매출']); c2.metric("영업",sm['영업']); c3.metric("순익",sm['순익']); st.caption(f"기준: {sm['title']}")
                
                st.divider(); st.markdown("**최근 1년 주요 공시**")
                rpts = dart.list(final_corp, start=(datetime.now()-timedelta(days=365)).strftime('%Y-%m-%d'))
                if rpts is not None and not rpts.empty:
                    if "신탁" in search_txt or "자산" in search_txt: rpts = rpts[rpts['report_nm'].str.contains("신탁|계약|수주")]
                    for i, r in rpts.head(10).iterrows():
                        st.markdown(f"- [{r['report_nm']}](http://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}) ({r['rcept_dt']})")
                else: st.info("공시 없음")
            except: st.error("분석 실패")

# ---------------------------------------------------------
# [탭 3] 건설/부동산 통계 (속보 버전) - NEW!
# ---------------------------------------------------------
elif mode == "🏗️ 건설/부동산 통계 (속보)":
    st.title("🏗️ 대구/경북 통계 자료 & 속보")
    st.markdown("**통계청 API 대신 뉴스/발표자료 링크를 직접 모아준다. 속도 0.1초!**")

    # 1. 공식 사이트 바로가기 버튼
    st.markdown("### 🔗 공식 데이터 원문 바로가기")
    c1, c2, c3, c4 = st.columns(4)
    c1.link_button("📉 국토부 통계누리 (미분양)", "http://stat.molit.go.kr/")
    c2.link_button("🏠 부동산원 R-ONE (거래량)", "https://www.r-one.co.kr/")
    c3.link_button("🏗️ 세움터 (건축허가)", "https://www.eais.go.kr/")
    c4.link_button("🦁 대구시 통계포털", "https://stat.daegu.go.kr/")
    
    st.divider()

    # 2. 통계 뉴스 피드 (탭 구성)
    t1, t2, t3, t4 = st.tabs(["📉 미분양 속보", "🏗️ 건축허가/수주", "🏠 매매/거래 동향", "🏢 준공/입주 물량"])
    
    # 공통 뉴스 렌더링 함수
    def render_stat_news(keywords):
        with st.spinner("최신 발표 자료 찾는 중..."):
            news = get_news(keywords) # 뉴스 함수 재활용
        
        if news:
            # 최신순 10개만
            for n in news[:10]:
                with st.expander(f"({n['published'].strftime('%m/%d')}) {n['title']}"):
                    st.write(n['summary'])
                    st.link_button("기사 원문 보기", n['link'])
        else:
            st.info("관련 최신 기사가 없다.")

    with t1:
        st.subheader("📉 대구/경북 미분양 현황 발표")
        render_stat_news(["대구 미분양 통계", "경북 미분양 주택 현황", "대구 준공후 미분양", "국토부 미분양 발표"])
    
    with t2:
        st.subheader("🏗️ 대구/경북 건축허가 및 수주 동향")
        render_stat_news(["대구 건축허가 면적 통계", "대구 주택 인허가 실적", "대구 건설 수주액 통계", "경북 건축 착공 통계"])

    with t3:
        st.subheader("🏠 아파트 매매 거래량 및 시장 동향")
        render_stat_news(["대구 아파트 매매 거래량", "대구 부동산 시장 동향", "부동산원 주택 거래 현황", "대구 아파트 실거래가 지수"])

    with t4:
        st.subheader("🏢 주택 준공 실적 및 입주 물량")
        render_stat_news(["대구 아파트 입주 물량", "대구 주택 준공 실적 통계", "대구 입주 경기 전망", "경북 아파트 입주"])
