import streamlit as st
import feedparser
import ssl
import urllib.parse
import re
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import OpenDartReader 
from datetime import datetime, timedelta
from dateutil import parser

# ---------------------------------------------------------
# 1. 설정 & 스타일
# ---------------------------------------------------------
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

st.set_page_config(
    page_title="영업용 통합 대시보드",
    page_icon="💼",
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
        .metric-box {
            background-color: #f0f2f6; padding: 15px; border-radius: 8px;
            text-align: center; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        }
        a { text-decoration: none; color: #0068c9; font-weight: bold; }
        a:hover { text-decoration: underline; }
    </style>
""", unsafe_allow_html=True)

# [중요] API 키 (DART 필수)
DART_API_KEY = "3522c934d5547db5cba3f51f8d832e1a82ebce55"

# ---------------------------------------------------------
# 2. 사이드바
# ---------------------------------------------------------
try: st.sidebar.image("logo.png", use_column_width=True)
except: pass

st.sidebar.header("🚀 메뉴 선택")
# 통계 탭 삭제하고 2개로 통합
mode = st.sidebar.radio("", ["📰 뉴스 모니터링", "🏢 기업 공시 & 재무제표"])

# ---------------------------------------------------------
# 3. 공통 함수
# ---------------------------------------------------------
def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)[:150] + "..." 

@st.cache_data(ttl=3600) # 1시간 캐싱
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
    # 최근 2개년도 데이터 탐색
    years = [2025, 2024]
    codes = [('11011','사업보고서'), ('11014','3분기'), ('11012','반기'), ('11013','1분기')]
    
    for year in years:
        for code, c_name in codes:
            try:
                fs = dart.finstate(corp_name, year, reprt_code=code)
                if fs is None or fs.empty: continue
                
                # 연결(CFS) 우선, 없으면 개별(OFS)
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
                
                if sn == "-": continue # 매출 없으면 다음 기간 검색
                return {"title": f"{year}년 {c_name}", "매출":sn, "영업":on, "순익":nn}
            except: continue
    return None

# ---------------------------------------------------------
# [탭 1] 뉴스 모니터링 (통계 키워드 통합됨!)
# ---------------------------------------------------------
if mode == "📰 뉴스 모니터링":
    st.title("💼 B2B 영업 인텔리전스")
    
    # 1. 통합된 키워드셋
    preset_hotel = "호텔 리모델링, 신규 호텔 오픈, 리조트 착공, 5성급 호텔 리뉴얼, 호텔 FF&E, 생활숙박시설 분양, 호텔 매각, 샌즈"
    preset_market = "건자재 가격, 친환경 자재, 모듈러 주택, 현대건설 수주, GS건설 수주, 디엘건설, 디엘이앤씨, 현대엔지니어링"
    preset_office = "사옥 이전, 통합 사옥 건립, 스마트 오피스, 기업 연수원 건립, 공공청사 리모델링, 공유 오피스 출점, 오피스 인테리어, 데이터센터"
    
    # [핵심] 여기에 통계/속보 관련 키워드 대거 추가함
    preset_trend = (
        "건설산업연구원 전망, 대한건설협회 수주, 대구 미분양 주택, 경북 미분양 현황, "
        "대구 아파트 입주 물량, 대구 주택 준공 실적, 아파트 매매 거래량, "
        "대구 건축허가 면적, 건설 수주액 통계, 미분양 관리지역 선정"
    )
    
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
        if st.button("📈 건설경기/통계"): st.session_state['search_keywords'] = preset_trend # 이름 변경
        if st.button("🔥 전체 풀세트"): st.session_state['search_keywords'] = preset_all
    
    user_input = st.sidebar.text_area("검색 키워드 (쉼표로 구분)", key='search_keywords', height=100)
    keywords = [k.strip() for k in user_input.split(',') if k.strip()]
    
    # 기간 선택 기능
    period = st.sidebar.selectbox("기간", ["전체 보기", "최근 24시간", "최근 3일", "최근 1주일", "최근 1개월", "최근 3개월"])
    
    if st.button("🔄 뉴스 새로고침"): st.cache_data.clear()

    with st.spinner('뉴스 수집 중...'):
        news = get_news(keywords)
    news.sort(key=lambda x: x['published'], reverse=True)
    
    # 기간 필터링
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

    if not final: st.warning("조건에 맞는 뉴스가 없다.")
    else:
        st.divider()
        # 키워드별 뉴스 개수 차트
        cnt = pd.DataFrame(final)['keyword'].value_counts().reset_index()
        cnt.columns=['키워드','개수']
        fig = px.bar(cnt, x='개수', y='키워드', orientation='h', text='개수', color='개수', color_continuous_scale='Teal')
        fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', xaxis_title="", yaxis_title="", height=250, margin=dict(t=0,b=0,l=0,r=0))
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader(f"총 {len(final)}건의 뉴스")
        for n in final:
            with st.expander(f"({n['published'].strftime('%m/%d')}) [{n['keyword']}] {n['title']}"):
                st.info(n['summary'])
                st.link_button("기사 원문 보기", n['link'])

# ---------------------------------------------------------
# [탭 2] 기업 공시 & 재무제표 (기능 복구 완료!)
# ---------------------------------------------------------
elif mode == "🏢 기업 공시 & 재무제표":
    st.title("🏢 기업 분석 (상장사 + 신탁사)")
    
    search_txt = st.text_input("회사명 또는 종목코드", placeholder="예: 한국토지신탁, 034830")
    
    if st.button("🚀 분석 시작"):
        with st.spinner("DART 시스템 접속 및 분석 중..."):
            dart = get_dart_system()
            
            if dart:
                try:
                    final_corp = None; stock_code = None
                    
                    # 1. 종목코드로 검색
                    if search_txt.isdigit() and len(search_txt) >= 6:
                        final_corp = search_txt; stock_code = search_txt
                    else:
                        # 2. 이름으로 검색 (포함 검색)
                        cdf = dart.corp_codes
                        cands = cdf[cdf['corp_name'].str.contains(search_txt)]
                        if not cands.empty:
                            # 첫 번째 결과 선택
                            final_corp = cands.iloc[0]['corp_code']
                            stock_code = cands.iloc[0]['stock_code'] if cands.iloc[0]['stock_code'] else None
                        else:
                            final_corp = search_txt # 없으면 입력값 그대로 시도

                    # 결과 출력 시작
                    st.divider()
                    st.subheader(f"📊 {search_txt} 분석 결과")
                    
                    # (1) 주가 차트 (상장사만 나옴)
                    if stock_code and stock_code.strip():
                        res = get_stock_chart(stock_code)
                        if res:
                            f, l, c = res
                            st.metric("현재가", f"{l:,}원", f"{c:.2f}%")
                            st.plotly_chart(f, use_container_width=True)
                    
                    # (2) 재무 요약 (DART)
                    sm = get_financial_summary_advanced(dart, final_corp)
                    if sm:
                        c1, c2, c3 = st.columns(3)
                        c1.metric("매출", sm['매출'])
                        c2.metric("영업이익", sm['영업'])
                        c3.metric("순이익", sm['순익'])
                        st.caption(f"기준: {sm['title']} (연결/개별 자동 선택)")
                    else:
                        st.warning("재무 데이터를 가져올 수 없습니다. (비상장사이거나 데이터 없음)")
                    
                    # (3) 최근 공시 (1년치)
                    st.divider()
                    st.markdown("**📅 최근 1년 주요 공시**")
                    rpts = dart.list(final_corp, start=(datetime.now()-timedelta(days=365)).strftime('%Y-%m-%d'))
                    
                    if rpts is not None and not rpts.empty:
                        # 신탁사일 경우 수주/계약 관련만 필터링해서 보여주면 편함
                        if "신탁" in search_txt or "자산" in search_txt:
                            st.caption("※ 신탁사는 수주/계약/신탁 관련 공시 우선 표시")
                            rpts_filtered = rpts[rpts['report_nm'].str.contains("신탁|계약|수주|도급")]
                            if rpts_filtered.empty: rpts_filtered = rpts # 없으면 전체 표시
                            rpts = rpts_filtered
                        
                        for i, r in rpts.head(10).iterrows(): # 10개만 표시
                            link = f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}"
                            st.markdown(f"- [{r['report_nm']}]({link}) <span style='color:gray'>({r['rcept_dt']})</span>", unsafe_allow_html=True)
                    else:
                        st.info("최근 1년 내 공시가 없습니다.")

                except Exception as e:
                    st.error(f"분석 중 오류 발생: {e}")
                    st.info("회사명을 정확히 입력했는지 확인해주세요.")
            else:
                st.error("DART API 연결 실패. API 키를 확인해주세요.")
