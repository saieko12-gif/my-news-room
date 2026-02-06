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
from datetime import datetime, timedelta
from dateutil import parser

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
        .stButton button { height: 2.5rem; padding-top: 0; padding-bottom: 0; } 
        a { text-decoration: none; color: #0068c9; font-weight: bold; }
        a:hover { text-decoration: underline; }
    </style>
""", unsafe_allow_html=True)

# [중요] 니 API 키
DART_API_KEY = "3522c934d5547db5cba3f51f8d832e1a82ebce55"

# ---------------------------------------------------------
# 2. 사이드바
# ---------------------------------------------------------
try: st.sidebar.image("logo.png", use_column_width=True)
except: pass

st.sidebar.header("🛠️ 설정")
mode = st.sidebar.radio("모드 선택", ["📰 뉴스 모니터링", "🏢 기업 공시 & 재무제표"])

# [신규 기능] 회사 목록 강제 갱신 버튼
st.sidebar.markdown("---")
st.sidebar.markdown("**데이터 관리**")
if st.sidebar.button("🔄 회사 목록 강제 갱신"):
    st.cache_resource.clear() # 캐시 삭제
    st.success("회사 목록을 초기화했다! 다시 검색해봐라.")

# ---------------------------------------------------------
# 3. 공통 함수
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
        # OpenDartReader 객체 생성 시 회사 목록을 다운로드함
        # 기타법인까지 모두 포함된 리스트임
        dart = OpenDartReader(DART_API_KEY) 
        return dart
    except Exception as e:
        return None

def get_financial_summary_advanced(dart, corp_name):
    years = [2025, 2024]
    codes = [('11011','사업보고서'), ('11014','3분기'), ('11012','반기'), ('11013','1분기')]
    
    for year in years:
        for code, c_name in codes:
            try:
                fs = dart.finstate(corp_name, year, reprt_code=code)
                if fs is None or fs.empty: continue
                
                target_fs = fs[fs['fs_div']=='CFS']
                if target_fs.empty: target_fs = fs[fs['fs_div']=='OFS']

                def get_val(names):
                    for nm in names:
                        row = target_fs[target_fs['account_nm']==nm]
                        if not row.empty:
                            try:
                                t_str = row.iloc[0].get('thstrm_add_amount', row.iloc[0]['thstrm_amount'])
                                if pd.isna(t_str) or t_str=='': t_str = row.iloc[0]['thstrm_amount']
                                p_str = row.iloc[0].get('frmtrm_add_amount', row.iloc[0]['frmtrm_amount'])
                                if pd.isna(p_str) or p_str=='': p_str = row.iloc[0]['frmtrm_amount']
                                
                                tv = float(str(t_str).replace(',',''))
                                pv = 0 if (pd.isna(p_str) or p_str=='') else float(str(p_str).replace(',',''))
                                
                                delta = f"{((tv-pv)/pv)*100:.1f}%" if pv!=0 else None
                                return "{:,} 억".format(int(tv/100000000)), delta, "{:,} 억".format(int(pv/100000000))
                            except: continue
                    return "-", None, "-"

                s_n, s_d, s_p = get_val(['매출액', '수익(매출액)'])
                if s_n == "-": continue
                o_n, o_d, o_p = get_val(['영업이익', '영업이익(손실)'])
                n_n, n_d, n_p = get_val(['당기순이익', '당기순이익(손실)'])

                rcept_no = ""
                try:
                    rl = dart.list(corp_name, start=f"{year}-01-01", end=f"{year}-12-31", kind='A')
                    kw = "사업보고서" if code=='11011' else ("분기" if code=='11014' else "반기")
                    for i, r in rl.iterrows():
                        if kw in r['report_nm']: 
                            rcept_no = r['rcept_no']; break
                except: pass

                return {"title": f"{year}년 {c_name} (누적)", "매출":(s_n,s_d,s_p), "영업":(o_n,o_d,o_p), "순익":(n_n,n_d,n_p), "link":rcept_no}
            except: continue
    return None

def get_stock_chart(target, code):
    try:
        df = fdr.DataReader(code, datetime.now()-timedelta(days=365), datetime.now())
        if df.empty: return None
        last = df['Close'].iloc[-1]; prev = df['Close'].iloc[-2]
        chg = ((last-prev)/prev)*100
        color = '#ff4b4b' if chg>0 else '#4b4bff'
        fig = px.area(df, x=df.index, y='Close')
        fig.update_layout(xaxis_title="", yaxis_title="", height=300, margin=dict(t=30,b=0,l=0,r=0), showlegend=False)
        fig.update_traces(line_color=color)
        return fig, last, chg
    except: return None

# ---------------------------------------------------------
# [탭 1] 뉴스
# ---------------------------------------------------------
if mode == "📰 뉴스 모니터링":
    st.title("💼 B2B 영업 인텔리전스")
    
    preset_hotel = "호텔 리모델링, 신규 호텔 오픈, 리조트 착공, 5성급 호텔 리뉴얼, 호텔 FF&E, 생활숙박시설 분양, 호텔 매각, 샌즈"
    preset_office = "사옥 이전, 통합 사옥 건립, 스마트 오피스, 기업 연수원 건립, 공공청사 리모델링, 공유 오피스 출점, 오피스 인테리어, 데이터센터"
    preset_market = "건자재 가격, 친환경 자재, 모듈러 주택, 현대건설 수주, GS건설 수주, 디엘건설, 디엘이앤씨, 현대엔지니어링"
    preset_all = f"{preset_hotel}, {preset_office}, {preset_market}"

    if 'search_keywords' not in st.session_state: st.session_state['search_keywords'] = preset_hotel
    st.sidebar.subheader("⚡ 키워드 자동 완성")
    c1, c2 = st.sidebar.columns(2)
    with c1:
        if st.button("🏨 호텔/리조트"): st.session_state['search_keywords'] = preset_hotel
        if st.button("🏗️ 건자재/동향"): st.session_state['search_keywords'] = preset_market
    with c2:
        if st.button("🏢 오피스/사옥"): st.session_state['search_keywords'] = preset_office
        if st.button("🔥 영업 풀세트"): st.session_state['search_keywords'] = preset_all
    
    user_input = st.sidebar.text_area("검색 키워드", key='search_keywords', height=100)
    keywords = [k.strip() for k in user_input.split(',') if k.strip()]
    period = st.sidebar.selectbox("기간", ["최근 24시간", "최근 3일", "최근 1주일"])
    
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
    st.title("🏢 기업 분석 (상장사 + 기타법인)")
    
    dart = get_dart_system()
    if dart is None: st.error("API 연결 실패. 키 확인 필요")
    else:
        search_txt = st.text_input("회사명 또는 종목코드", placeholder="예: 쿠팡, 야놀자, 현대건설")
        final_corp = None
        stock_code = None

        if search_txt:
            # 1. 종목코드로 검색
            if search_txt.isdigit() and len(search_txt) >= 6:
                final_corp = search_txt
                stock_code = search_txt
                st.info(f"🔢 코드검색: {search_txt}")
            else:
                try:
                    # 2. 이름으로 검색 (기타법인 포함 전체 리스트 탐색)
                    # 공백 제거 후 검색하는 로직 추가 (사용자가 '현대 건설'로 쳐도 찾게)
                    corp_df = dart.corp_codes
                    
                    # 검색어 정제 (공백 제거)
                    clean_search = search_txt.replace(" ", "")
                    
                    # 회사명 리스트에서 공백 제거한 것과 매칭되는지 확인 (느슨한 검색)
                    # 'corp_name' 컬럼을 문자열로 변환 후 검색
                    mask = corp_df['corp_name'].astype(str).str.replace(" ", "").str.contains(clean_search)
                    candidates = corp_df[mask]

                    if not candidates.empty:
                        # 결과가 너무 많으면 50개만 보여줌
                        show_list = candidates['corp_name'].tolist()[:50]
                        sel_name = st.selectbox(f"검색 결과 ({len(candidates)}개)", show_list)
                        
                        # 선택된 회사의 정보 추출
                        sel_row = candidates[candidates['corp_name'] == sel_name].iloc[0]
                        final_corp = sel_row['corp_code'] # DART 고유코드 사용 (이게 제일 정확함)
                        
                        # 상장사면 주식코드 있음
                        if not pd.isna(sel_row['stock_code']) and sel_row['stock_code'] != '':
                            stock_code = sel_row['stock_code']
                        
                        st.success(f"선택됨: **{sel_name}** (고유코드: {final_corp})")
                        
                        # 세션에 이름 저장 (표시용)
                        st.session_state['display_name'] = sel_name
                    else:
                        st.warning("목록에 없다. (좌측 '회사 목록 갱신' 버튼 눌러봤나?)")
                        if st.checkbox("강제 조회 (정확한 이름 입력 필수)"): 
                            final_corp = search_txt
                            st.session_state['display_name'] = search_txt
                except: 
                    final_corp = search_txt
                    st.session_state['display_name'] = search_txt

        if st.button("🚀 분석 시작"):
            st.session_state['active'] = True
            st.session_state['corp'] = final_corp
            st.session_state['sc'] = stock_code

        if st.session_state.get('active'):
            tgt = st.session_state.get('corp') # 이게 DART 코드거나 이름
            sc = st.session_state.get('sc')
            d_name = st.session_state.get('display_name', tgt)

            if tgt != final_corp: st.warning("⚠️ 대상 변경됨. 버튼 다시 클릭!")
            else:
                # A. 주가
                if sc:
                    st.divider()
                    st.subheader(f"📈 {d_name} 주가")
                    res = get_stock_chart(d_name, sc)
                    if res:
                        fig, last, chg = res
                        st.metric("현재가", f"{last:,}원", f"{chg:.2f}%")
                        st.plotly_chart(fig, use_container_width=True)
                    else: st.info("주가 정보 없음 (거래정지 혹은 데이터 부족)")
                else:
                    st.divider()
                    st.info(f"💡 **{d_name}**은(는) 비상장사(기타법인)라 주가 차트가 없다.")

                # B. 재무
                st.divider()
                st.subheader("💰 재무 성적표")
                summ = get_financial_summary_advanced(dart, tgt) # tgt가 고유코드면 더 정확함
                if summ:
                    st.markdown(f"**📌 {summ['title']}** (전년 대비)")
                    c1,c2,c3 = st.columns(3)
                    c1.metric("매출(누적)", summ['매출'][0], summ['매출'][1]); c1.caption(f"작년: {summ['매출'][2]}")
                    c2.metric("영업이익", summ['영업'][0], summ['영업'][1]); c2.caption(f"작년: {summ['영업'][2]}")
                    c3.metric("순이익", summ['순익'][0], summ['순익'][1]); c3.caption(f"작년: {summ['순익'][2]}")
                    if summ['link']: st.link_button("📄 원문 보고서", f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={summ['link']}")
                else: st.warning("재무 데이터 없음 (지주사거나 연결재무제표 미작성 등)")

                # C. 공시
                st.divider()
                st.subheader("📋 공시 내역")
                try:
                    end = datetime.now(); start = end - timedelta(days=365)
                    # tgt가 고유코드(8자리)면 이름 충돌 없이 정확하게 검색됨
                    rpts = dart.list(tgt, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))
                    
                    if rpts is None or rpts.empty: st.error("공시 없음")
                    else:
                        fq = st.text_input("🔍 결과 내 검색", placeholder="수주, 계약...")
                        if fq: rpts = rpts[rpts['report_nm'].str.contains(fq)]
                        
                        st.success(f"{len(rpts)}건 발견")
                        h1, h2 = st.columns([1.5, 8.5])
                        h1.markdown("**날짜**"); h2.markdown("**제목 (제출인)**"); st.markdown("---")
                        
                        for i, r in rpts.iterrows():
                            dt = r['rcept_dt']; fd = f"{dt[2:4]}/{dt[4:6]}/{dt[6:]}"
                            lk = f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}"
                            c1, c2 = st.columns([1.5, 8.5])
                            c1.text(fd)
                            c2.markdown(f"[{r['report_nm']}]({lk}) <span style='color:grey; font-size:0.8em'>({r['flr_nm']})</span>", unsafe_allow_html=True)
                            st.markdown("<hr style='margin: 3px 0; border-top: 1px solid #eee;'>", unsafe_allow_html=True)
                except: st.error("공시 로딩 실패")
