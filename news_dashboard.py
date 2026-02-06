import streamlit as st
import feedparser
import ssl
import urllib.parse
import re
import pandas as pd
import plotly.express as px
# OpenDartReader는 속도를 위해 아래 함수 안으로 숨김
import FinanceDataReader as fdr
from PublicDataReader import Kosis 
from datetime import datetime, timedelta
from dateutil import parser
from dateutil.relativedelta import relativedelta 

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
        }
    </style>
""", unsafe_allow_html=True)

# [중요] API 키
DART_API_KEY = "3522c934d5547db5cba3f51f8d832e1a82ebce55"
KOSIS_API_KEY = "ZDIxY2M0NTFmZThmNTZmNWZkOGYwYzYyNTMxMGIyNjg="

# ---------------------------------------------------------
# 2. 사이드바
# ---------------------------------------------------------
try: st.sidebar.image("logo.png", use_column_width=True)
except: pass

st.sidebar.header("🚀 모드 선택")
mode = st.sidebar.radio("", ["📰 뉴스 모니터링", "🏢 기업 공시 & 재무제표", "🏗️ 건설/부동산 통계"])

# ---------------------------------------------------------
# 3. 핵심 함수 (최적화)
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

# [⚡초고속 로직] 받자마자 '주요 지역' 빼고 다 버림
@st.cache_data(ttl=86400, show_spinner=False) 
def get_kosis_fast(org_id, tbl_id):
    try:
        api = Kosis(KOSIS_API_KEY)
        # 데이터 양 최소화 (최근 6개월)
        end_date = datetime.now().strftime("%Y%m")
        start_date = (datetime.now() - relativedelta(months=6)).strftime("%Y%m")
        
        df = api.get_data("KOSIS통합검색", orgId=org_id, tblId=tbl_id, startPrdDe=start_date, endPrdDe=end_date, prdSe="M")
        
        if df is not None:
            # [필터링] 전국 + 광역시 + 도 (총 18개)만 남기고 싹 삭제
            major_regions = ["전국", "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
            # 데이터에 포함된 지역명 중 major_regions에 있는 것만 필터링 (startswith로 처리하여 '서울특별시' 등도 커버)
            mask = df['C1_NM'].apply(lambda x: any(r in x for r in major_regions))
            df = df[mask]
            
        return df
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
    preset_trend = "건설산업연구원 전망, 대한건설협회 수주, 건축 착공 면적, 건설 수주액, 인테리어 시장 전망, 건축허가 면적, 주택 인허가 실적, 아파트 매매 거래량, 미분양 관리지역, 노후계획도시 특별법"
    preset_pf = "부동산 신탁 수주, 신탁계약 체결, 리츠 인가, PF 대출 보증, 시행사 시공사 선정, 대구 재개발 수주, 부동산 PF 조달, 브릿지론 본PF 전환, 그린리모델링 사업"
    preset_all = f"{preset_hotel}, {preset_trend}, {preset_pf}"

    if 'search_keywords' not in st.session_state: st.session_state['search_keywords'] = preset_hotel
    st.sidebar.subheader("⚡ 키워드 자동 완성")
    
    c1, c2 = st.sidebar.columns(2)
    with c1:
        if st.button("🏨 호텔/리조트"): st.session_state['search_keywords'] = preset_hotel
        if st.button("💰 PF/신탁/금융"): st.session_state['search_keywords'] = preset_pf
    with c2:
        if st.button("📈 건설경기 동향"): st.session_state['search_keywords'] = preset_trend
        if st.button("🔥 전체 풀세트"): st.session_state['search_keywords'] = preset_all
    
    user_input = st.sidebar.text_area("검색 키워드", key='search_keywords', height=100)
    keywords = [k.strip() for k in user_input.split(',') if k.strip()]
    
    if st.button("🔄 뉴스 새로고침"): st.cache_data.clear()

    with st.spinner('뉴스 긁어오는 중...'):
        news = get_news(keywords)
    news.sort(key=lambda x: x['published'], reverse=True)
    
    final = []
    now = datetime.now(news[0]['published'].tzinfo) if news else datetime.now()
    for n in news:
        if now - n['published'] <= timedelta(days=30): final.append(n)

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
# [탭 3] 건설/부동산 통계 (초고속 필터링 버전)
# ---------------------------------------------------------
elif mode == "🏗️ 건설/부동산 통계":
    st.title("🏗️ 대구/경북 건설 영업 대시보드")
    st.markdown("**전국 / 주요 광역시 / 도별 (17개 지역)** 핵심 요약판")

    t1, t2, t3, t4 = st.tabs(["📉 미분양 (위험)", "🏗️ 건축허가 (미래일감)", "🏠 매매거래 (리모델링)", "🏢 준공실적 (입주)"])

    def render_dashboard(stat_name, org_id, tbl_id, unit):
        with st.spinner(f"{stat_name} 데이터 가져오는 중... (최근 6개월)"):
            df = get_kosis_fast(org_id, tbl_id)
        
        if df is not None:
            if 'DT' in df.columns:
                df['DT'] = pd.to_numeric(df['DT'], errors='coerce')
                latest_date = df['PRD_DE'].max()
                latest_df = df[df['PRD_DE'] == latest_date]
                
                # 1. 핵심 지표 (Metric)
                try:
                    # 데이터에 '대구', '경북' 등 정확한 명칭이 있는지 확인 (포함 검색)
                    val_nat = latest_df[latest_df['C1_NM'].str.contains('전국')]['DT'].values[0]
                    val_dg = latest_df[latest_df['C1_NM'].str.contains('대구')]['DT'].values[0]
                    val_kb = latest_df[latest_df['C1_NM'].str.contains('경북')]['DT'].values[0]
                    
                    st.subheader(f"📅 {latest_date} 현황")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("🇰🇷 전국 총계", f"{val_nat:,.0f} {unit}")
                    c2.metric("🦁 대구", f"{val_dg:,.0f} {unit}")
                    c3.metric("🚜 경북", f"{val_kb:,.0f} {unit}")
                except: st.warning("핵심 지역 데이터 매칭 중 오류 발생")

                st.markdown("---")

                # 2. 전국 17개 시도 비교 차트
                st.subheader(f"📊 전국 17개 시/도 비교")
                # 전국 합계 빼고 나머지 지역만
                chart_df = latest_df[~latest_df['C1_NM'].str.contains('전국')].sort_values('DT', ascending=False)
                
                # 대구/경북 빨간색 강조
                colors = ['#e0e0e0'] * len(chart_df)
                regions = chart_df['C1_NM'].tolist()
                for i, r in enumerate(regions):
                    if '대구' in r or '경북' in r: colors[i] = '#ff4b4b'
                
                fig = go.Figure(data=[go.Bar(x=chart_df['C1_NM'], y=chart_df['DT'], text=chart_df['DT'], marker_color=colors)])
                fig.update_layout(height=350, margin=dict(l=0,r=0,t=30,b=0))
                st.plotly_chart(fig, use_container_width=True)

                # 3. 6개월 추세선
                st.subheader("📈 최근 6개월 추이")
                trend_regions = ["전국", "대구", "경북"]
                trend_df = df[df['C1_NM'].apply(lambda x: any(tr in x for tr in trend_regions))].sort_values('PRD_DE')
                fig_line = px.line(trend_df, x='PRD_DE', y='DT', color='C1_NM', markers=True)
                st.plotly_chart(fig_line, use_container_width=True)

            else: st.error("데이터 형식 오류")
        else: st.error("통계청 연결 실패. 잠시 후 다시.")

    with t1: render_dashboard("미분양 주택", "11601", "DT_1YL202001E", "호")
    with t2: render_dashboard("건축허가 면적", "11601", "DT_11601_202005", "㎡")
    with t3: render_dashboard("아파트 매매 거래", "40801", "DT_40801_26", "호")
    with t4: render_dashboard("주택 준공 실적", "11601", "DT_11601_202004", "호")
