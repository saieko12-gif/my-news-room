import streamlit as st
import feedparser
import ssl
import urllib.parse
import re
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import OpenDartReader
import FinanceDataReader as fdr
from PublicDataReader import Kosis 
from datetime import datetime, timedelta
from dateutil import parser
from dateutil.relativedelta import relativedelta # 날짜 계산용

# ---------------------------------------------------------
# 1. 설정 & 스타일
# ---------------------------------------------------------
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

st.set_page_config(
    page_title="영업용 뉴스 & 공시 수집기",
    page_icon="💼",
    layout="wide"
)

st.markdown("""
    <style>
        .block-container { padding-top: 3rem; } 
        div[data-testid="column"] { padding: 0 !important; } 
        hr { margin: 0.3rem 0 !important; } 
        .stButton button { 
            height: auto !important; 
            min-height: 2.5rem;
            padding-top: 5px !important; 
            padding-bottom: 5px !important; 
            font-size: 0.85rem !important; 
            white-space: normal !important; 
        }
        a { text-decoration: none; color: #0068c9; font-weight: bold; }
        a:hover { text-decoration: underline; }
    </style>
""", unsafe_allow_html=True)

# [중요] API 키 설정
DART_API_KEY = "3522c934d5547db5cba3f51f8d832e1a82ebce55"
KOSIS_API_KEY = "ZDIxY2M0NTFmZThmNTZmNWZkOGYwYzYyNTMxMGIyNjg="

# ---------------------------------------------------------
# 2. 사이드바
# ---------------------------------------------------------
try: st.sidebar.image("logo.png", use_column_width=True)
except: pass

st.sidebar.header("🛠️ 설정")
mode = st.sidebar.radio("모드 선택", ["📰 뉴스 모니터링", "🏢 기업 공시 & 재무제표", "🏗️ 건설/부동산 통계"])

# ---------------------------------------------------------
# 3. 데이터 수집 함수 (기간 필터링 기능 추가!)
# ---------------------------------------------------------
def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)[:150] + "..." 

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
            all_news.append({
                'keyword': term,
                'title': entry.title,
                'link': entry.link,
                'published': pub_date,
                'summary': clean_html(entry.get('description', '')),
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

# [속도 개선] 기간(start, end)을 받아서 그만큼만 긁어오도록 수정!
@st.cache_data(ttl=3600) 
def get_kosis_data_period(search_nm, start_date, end_date):
    try:
        api = Kosis(KOSIS_API_KEY)
        # KOSIS API 파라미터: startPrdDe, endPrdDe (YYYYMM 형식)
        df = api.get_data(
            "KOSIS통합검색", 
            searchNm=search_nm,
            startPrdDe=start_date,
            endPrdDe=end_date,
            prdSe="M" # 월별 데이터로 고정 (대부분의 건설 통계는 월별임)
        )
        return df
    except:
        return None

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
                                ps = r.iloc[0].get('frmtrm_add_amount', r.iloc[0]['frmtrm_amount'])
                                if pd.isna(ps) or ps=='': ps = r.iloc[0]['frmtrm_amount']
                                tv = float(str(ts).replace(',','')); pv = 0 if (pd.isna(ps) or ps=='') else float(str(ps).replace(',',''))
                                dt = f"{((tv-pv)/pv)*100:.1f}%" if pv!=0 else None
                                return "{:,} 억".format(int(tv/100000000)), dt, "{:,} 억".format(int(pv/100000000))
                            except: continue
                    return "-", None, "-"
                sn,sd,sp = gv(['매출액', '수익(매출액)'])
                if sn == "-": continue
                on,od,op = gv(['영업이익', '영업이익(손실)']); nn,nd,np = gv(['당기순이익', '당기순이익(손실)'])
                rn = ""
                try:
                    rl = dart.list(corp_name, start=f"{year}-01-01", end=f"{year}-12-31", kind='A')
                    kw = "사업보고서" if code=='11011' else ("분기" if code=='11014' else "반기")
                    for i,r in rl.iterrows():
                        if kw in r['report_nm']: rn = r['rcept_no']; break
                except: pass
                return {"title": f"{year}년 {c_name} (누적)", "매출":(sn,sd,sp), "영업":(on,od,op), "순익":(nn,nd,np), "link":rn}
            except: continue
    return None

def get_stock_chart(target, code):
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

# ---------------------------------------------------------
# [탭 1] 뉴스 모니터링
# ---------------------------------------------------------
if mode == "📰 뉴스 모니터링":
    st.title("💼 B2B 영업 인텔리전스")
    st.markdown("뉴스, 공시, 재무, 그리고 **주가 흐름**까지! **스마트한 영업맨의 비밀무기**")
    
    preset_hotel = "호텔 리모델링, 신규 호텔 오픈, 리조트 착공, 5성급 호텔 리뉴얼, 호텔 FF&E, 생활숙박시설 분양, 호텔 매각, 샌즈"
    preset_market = "건자재 가격, 친환경 자재, 모듈러 주택, 현대건설 수주, GS건설 수주, 디엘건설, 디엘이앤씨, 현대엔지니어링"
    preset_office = "사옥 이전, 통합 사옥 건립, 스마트 오피스, 기업 연수원 건립, 공공청사 리모델링, 공유 오피스 출점, 오피스 인테리어, 데이터센터"
    
    preset_trend = (
        "건설산업연구원 전망, 대한건설협회 수주, 건축 착공 면적, 건설 수주액, 인테리어 시장 전망, "
        "건축허가 면적, 주택 인허가 실적, 아파트 매매 거래량, 미분양 관리지역, 노후계획도시 특별법"
    )
    
    preset_pf = (
        "부동산 신탁 수주, 신탁계약 체결, 리츠 인가, PF 대출 보증, 시행사 시공사 선정, 대구 재개발 수주, "
        "부동산 PF 조달, 브릿지론 본PF 전환, 그린리모델링 사업"
    )

    preset_all = f"{preset_hotel}, {preset_office}, {preset_market}, {preset_trend}, {preset_pf}"

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

    with st.spinner('뉴스 수집 중...'):
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

    if not final: st.warning("뉴스 없음")
    else:
        st.divider()
        cnt = pd.DataFrame(final)['keyword'].value_counts().reset_index()
        cnt.columns=['키워드','개수']
        fig = px.bar(cnt, x='개수', y='키워드', orientation='h', text='개수', color='개수', color_continuous_scale='Teal')
        fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', xaxis_title="", yaxis_title="", height=250, margin=dict(t=0,b=0,l=0,r=0))
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        c1, c2 = st.columns([1, 2])
        q = c1.text_input("뉴스 검색")
        keys = list(set([n['keyword'] for n in final]))
        sel = c2.multiselect("필터", keys, keys)
        
        filtered = [n for n in final if n['keyword'] in sel and (not q or q in n['title'])]
        for n in filtered:
            with st.expander(f"({n['published'].strftime('%m/%d')}) [{n['keyword']}] {n['title']}"):
                if n['summary']: st.info(n['summary'])
                st.link_button("원문 보기", n['link'])

# ---------------------------------------------------------
# [탭 2] 기업 공시 & 재무제표
# ---------------------------------------------------------
elif mode == "🏢 기업 공시 & 재무제표":
    st.title("🏢 기업 분석 (상장사 + 신탁사)")
    
    dart = get_dart_system()
    if dart is None: st.error("API 연결 실패")
    else:
        search_txt = st.text_input("회사명 또는 종목코드", placeholder="예: 한국토지신탁, 034830")
        final_corp = None; stock_code = None

        if search_txt:
            if search_txt.isdigit() and len(search_txt) >= 6:
                final_corp = search_txt; stock_code = search_txt
            else:
                try:
                    cdf = dart.corp_codes
                    cln = search_txt.replace(" ", "")
                    msk = cdf['corp_name'].astype(str).str.replace(" ", "").str.contains(cln)
                    cands = cdf[msk]
                    if not cands.empty:
                        sl = cands['corp_name'].tolist()[:50]
                        sn = st.selectbox(f"검색 결과 ({len(cands)}개)", sl)
                        sr = cands[cands['corp_name'] == sn].iloc[0]
                        final_corp = sr['corp_code']
                        if not pd.isna(sr['stock_code']) and sr['stock_code'] != '': stock_code = sr['stock_code']
                        st.session_state['dn'] = sn
                    else:
                        st.warning("목록에 없음")
                        if st.checkbox("강제 조회"): final_corp = search_txt; st.session_state['dn'] = search_txt
                except: final_corp = search_txt; st.session_state['dn'] = search_txt

        if st.button("🚀 분석 시작"):
            st.session_state['act'] = True; st.session_state['cp'] = final_corp; st.session_state['sc'] = stock_code

        if st.session_state.get('act'):
            tgt = st.session_state.get('cp'); sc = st.session_state.get('sc'); dn = st.session_state.get('dn', tgt)
            if tgt != final_corp: st.warning("버튼 다시 클릭!")
            else:
                if sc:
                    st.divider(); st.subheader(f"📈 {dn} 주가")
                    res = get_stock_chart(dn, sc)
                    if res:
                        f, l, c = res; st.metric("현재가", f"{l:,}원", f"{c:.2f}%")
                        st.plotly_chart(f, use_container_width=True)
                    else: st.info("주가 정보 없음")
                else: st.divider(); st.info("비상장사라 주가 없음")

                st.divider(); st.subheader("💰 재무 성적표")
                sm = get_financial_summary_advanced(dart, tgt)
                if sm:
                    st.markdown(f"**📌 {sm['title']}** (전년 대비)")
                    c1,c2,c3 = st.columns(3)
                    c1.metric("매출(누적)", sm['매출'][0], sm['매출'][1]); c1.caption(f"작년: {sm['매출'][2]}")
                    c2.metric("영업이익", sm['영업'][0], sm['영업'][1]); c2.caption(f"작년: {sm['영업'][2]}")
                    c3.metric("순이익", sm['순익'][0], sm['순익'][1]); c3.caption(f"작년: {sm['순익'][2]}")
                    if sm['link']: st.link_button("📄 원문 보고서", f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={sm['link']}")
                else: st.warning("재무 데이터 없음")

                st.divider(); st.subheader("📋 공시 내역")
                try:
                    ed = datetime.now(); stt = ed - timedelta(days=365)
                    rpts = dart.list(tgt, start=stt.strftime('%Y-%m-%d'), end=ed.strftime('%Y-%m-%d'))
                    if rpts is None or rpts.empty: st.error("공시 없음")
                    else:
                        fq = st.text_input("🔍 결과 내 검색", placeholder="신탁, 수주, 계약...")
                        if fq: rpts = rpts[rpts['report_nm'].str.contains(fq)]
                        st.success(f"{len(rpts)}건 발견")
                        
                        if "신탁" in dn or "자산" in dn:
                            st.info("💡 **Tip:** 신탁사는 **'신탁계약'**이나 **'공사도급계약'**을 검색하면 현장 정보가 나온데이!")

                        h1, h2 = st.columns([1.5, 8.5]); h1.markdown("**날짜**"); h2.markdown("**제목 (제출인)**"); st.markdown("---")
                        for i, r in rpts.iterrows():
                            dt = r['rcept_dt']; fd = f"{dt[2:4]}/{dt[4:6]}/{dt[6:]}"
                            lk = f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}"
                            c1, c2 = st.columns([1.5, 8.5])
                            c1.text(fd)
                            c2.markdown(f"[{r['report_nm']}]({lk}) <span style='color:grey; font-size:0.8em'>({r['flr_nm']})</span>", unsafe_allow_html=True)
                            st.markdown("<hr style='margin: 3px 0; border-top: 1px solid #eee;'>", unsafe_allow_html=True)
                except: st.error("공시 로딩 실패")

# ---------------------------------------------------------
# [탭 3] 건설/부동산 통계
# ---------------------------------------------------------
elif mode == "🏗️ 건설/부동산 통계":
    st.title("🏗️ 건설 & 부동산 시장 통계")
    st.markdown("통계청(KOSIS) 데이터를 실시간으로 가져온데이. **영업의 미래는 숫자에 있다!**")
    
    # [수정] 기간 설정 옵션 추가
    col_p1, col_p2 = st.columns([1, 3])
    with col_p1:
        date_opt = st.selectbox("조회 기간 설정", ["최근 3년 (기본)", "최근 1년 (빠름)", "직접 입력"])
    
    # 날짜 계산 (YYYYMM 형식)
    now = datetime.now()
    if date_opt == "최근 3년 (기본)":
        start_date = (now - relativedelta(years=3)).strftime("%Y%m")
        end_date = now.strftime("%Y%m")
    elif date_opt == "최근 1년 (빠름)":
        start_date = (now - relativedelta(years=1)).strftime("%Y%m")
        end_date = now.strftime("%Y%m")
    else: # 직접 입력
        c_y1, c_y2 = st.columns(2)
        s_y = c_y1.text_input("시작 년월 (예: 202001)", value=(now - relativedelta(years=3)).strftime("%Y%m"))
        e_y = c_y2.text_input("종료 년월 (예: 202401)", value=now.strftime("%Y%m"))
        start_date = s_y
        end_date = e_y
    
    user_key = st.text_input("🔑 KOSIS API Key (비워두면 저장된 키 사용)", type="password")
    final_key = user_key if user_key else KOSIS_API_KEY
    
    stat_type = st.radio("보고 싶은 통계 선택", 
                         ["📉 미분양주택현황 (위험신호)", 
                          "🏗️ 건축허가면적 (선행지표)",
                          "🏠 주택매매거래현황 (리모델링 수요)",
                          "🏢 주택준공실적 (입주/가구수요)"], 
                         horizontal=True)
    
    if st.button("📊 데이터 가져오기"):
        # 함수 호출 시 start_date, end_date를 같이 넘김
        with st.spinner("통계청 서버 털어오는 중..."):
            
            # API 호출 함수 (내부적으로 캐싱)
            search_nm = ""
            if "미분양" in stat_type: search_nm = "미분양주택현황"
            elif "건축허가" in stat_type: search_nm = "건축허가현황"
            elif "주택매매" in stat_type: search_nm = "아파트매매거래현황"
            elif "주택준공" in stat_type: search_nm = "주택준공실적"
            
            df = get_kosis_data_period(search_nm, start_date, end_date)
            
            if df is not None:
                st.subheader(f"📊 {stat_type.split()[1]} ({start_date} ~ {end_date})")
                
                # 최신 데이터 날짜 확인
                latest_date = df['PRD_DE'].max()
                st.success(f"데이터 로딩 완료 (최신: {latest_date})")
                
                # 데이터 타입 변환 (문자 -> 숫자)
                df['DT'] = pd.to_numeric(df['DT'], errors='coerce')
                
                # 1. 최신 시점의 지역별 비교 (바 차트)
                target_df = df[df['PRD_DE'] == latest_date]
                chart_df = target_df[~target_df['C1_NM'].str.contains("전국|수도권|지방")]
                chart_df = chart_df.sort_values(by='DT', ascending=False).head(15)
                
                fig_bar = px.bar(chart_df, x='C1_NM', y='DT', text='DT', title=f"지역별 TOP 15 ({latest_date})", color='DT', color_continuous_scale='Blues')
                st.plotly_chart(fig_bar, use_container_width=True)
                
                # 2. 전국 기준 시계열 추이 (라인 차트)
                ts_df = df[df['C1_NM'] == '전국'].sort_values('PRD_DE')
                fig_line = px.line(ts_df, x='PRD_DE', y='DT', markers=True, title=f"전국 {stat_type.split()[1]} 추이")
                st.plotly_chart(fig_line, use_container_width=True)
                
                with st.expander("📄 원본 데이터 보기"): st.dataframe(df)
            else:
                st.error("데이터 못 가져왔다. (API 키 확인 또는 기간을 줄여봐라)")
