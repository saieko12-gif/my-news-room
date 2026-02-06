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

# 스타일 적용
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

# [중요] API 키
DART_API_KEY = "3522c934d5547db5cba3f51f8d832e1a82ebce55"

# ---------------------------------------------------------
# 2. 사이드바
# ---------------------------------------------------------
try: st.sidebar.image("logo.png", use_column_width=True)
except: pass

st.sidebar.header("🛠️ 설정")
mode = st.sidebar.radio("모드 선택", ["📰 뉴스 모니터링", "🏢 기업 공시 & 재무제표"])

# ---------------------------------------------------------
# 3. 공통 함수
# ---------------------------------------------------------
def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)[:150] + "..." 

# 제목 정규화 (중복 제거용)
def normalize_title(title):
    title = re.sub(r'\[.*?\]', '', title)
    title = title.split(' - ')[0]
    title = title.split(' | ')[0]
    title = title.split('...')[0]
    return title.strip()

@st.cache_data(ttl=600)
def get_news(search_terms):
    all_news = []
    seen_titles = set()

    for term in search_terms:
        encoded_term = urllib.parse.quote(term)
        url = f"https://news.google.com/rss/search?q={encoded_term}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        
        for entry in feed.entries:
            raw_title = entry.title
            clean_t = normalize_title(raw_title) 
            
            if clean_t in seen_titles: continue
            seen_titles.add(clean_t)
            
            try: pub_date = parser.parse(entry.published)
            except: pub_date = datetime.now()
            
            all_news.append({
                'keyword': term,
                'title': raw_title,
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

# [핵심] 재무제표 분석 강화 (현금흐름, 유동비율, 한줄평 추가)
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
                                tv = float(str(ts).replace(',',''))
                                pv = 0 if (pd.isna(ps) or ps=='') else float(str(ps).replace(',',''))
                                dt = f"{((tv-pv)/pv)*100:.1f}%" if pv!=0 else None
                                return tv, dt, pv, "{:,} 억".format(int(tv/100000000))
                            except: continue
                    return None, None, None, "-"

                # 1. 실적 (매출, 영업이익, 순이익)
                sn_val, sd, sp_val, sn_str = gv(['매출액', '수익(매출액)'])
                on_val, od, op_val, on_str = gv(['영업이익', '영업이익(손실)'])
                nn_val, nd, np_val, nn_str = gv(['당기순이익', '당기순이익(손실)'])
                
                if sn_str == "-": continue

                # 2. 안정성 (자산, 부채, 자본, 유동자산, 유동부채)
                assets_val, _, _, assets_str = gv(['자산총계'])
                liab_val, _, _, liab_str = gv(['부채총계'])
                equity_val, _, _, equity_str = gv(['자본총계'])
                
                curr_assets_val, _, _, _ = gv(['유동자산'])
                curr_liab_val, _, _, _ = gv(['유동부채'])

                # 3. 현금흐름 (영업활동현금흐름)
                cfo_val, _, _, cfo_str = gv(['영업활동현금흐름', '영업활동으로인한현금흐름'])

                # 4. 비율 계산
                opm = 0; debt_ratio = 0; curr_ratio = 0
                if sn_val and sn_val != 0: opm = (on_val / sn_val) * 100
                if equity_val and equity_val != 0: debt_ratio = (liab_val / equity_val) * 100
                if curr_liab_val and curr_liab_val != 0: curr_ratio = (curr_assets_val / curr_liab_val) * 100

                # 5. [AI 한줄평 로직] - 경상도 버전
                comments = []
                
                # 실적 평가
                if sd and float(sd.replace('%','')) > 0: comments.append("매출이 늘어가 성장세가 좋고")
                else: comments.append("매출이 쪼매 줄어들긴 했지만")
                
                if on_val and on_val > 0: comments.append("돈도(영업이익) 흑자로 잘 벌고 있네.")
                else: comments.append("영업이익이 적자라 쪼매 아쉽네.")

                # 재무/현금 평가
                risk_msg = ""
                if cfo_val and cfo_val > 0: 
                    if curr_ratio >= 100: risk_msg = "현금도 잘 돌고 지갑(유동비율)도 빵빵해서 튼튼하다!"
                    else: risk_msg = "현금은 도는데 당장 쓸 돈(유동비율)은 좀 챙기야겠네."
                else:
                    if curr_ratio >= 100: risk_msg = "현금흐름은 마이너스지만 모아둔 돈(유동자산)은 있어서 버틸만하다."
                    else: risk_msg = "❗ 마, 현금도 안 돌고 지갑도 얇다. 수금(결제) 조심해라!"
                
                comments.append(risk_msg)
                one_line_summary = " ".join(comments)

                rn = ""
                try:
                    rl = dart.list(corp_name, start=f"{year}-01-01", end=f"{year}-12-31", kind='A')
                    kw = "사업보고서" if code=='11011' else ("분기" if code=='11014' else "반기")
                    for i,r in rl.iterrows():
                        if kw in r['report_nm']: rn = r['rcept_no']; break
                except: pass
                
                return {
                    "title": f"{year}년 {c_name} (누적)", 
                    "매출": (sn_str, sd, "{:,} 억".format(int(sp_val/100000000)) if sp_val else "-"), 
                    "영업": (on_str, od, "{:,} 억".format(int(op_val/100000000)) if op_val else "-"), 
                    "순익": (nn_str, nd, "{:,} 억".format(int(np_val/100000000)) if np_val else "-"),
                    "자산": assets_str,
                    "부채비율": f"{debt_ratio:.1f}%",
                    "영업이익률": f"{opm:.1f}%",
                    "현금흐름": cfo_str,
                    "유동비율": f"{curr_ratio:.1f}%",
                    "한줄평": one_line_summary,
                    "link": rn
                }
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
    preset_office = "사옥 이전, 통합 사옥 건립, 스마트 오피스, 기업 연수원 건립, 공공청사 리모델링, 공유 오피스 출점, 오피스 인테리어, 데이터센터"
    
    preset_market = (
        "친환경 자재, 현대건설 수주, GS건설 수주, 디엘건설, 디엘이앤씨, "
        "현대엔지니어링, 삼성물산 수주, 대우건설 수주, 세라믹 자재, 건설자재, 건자재"
    )
    
    preset_trend = (
        "미분양 주택, 미분양 현황, 아파트 입주 물량, 주택 준공 실적, "
        "건축허가 면적, 아파트 매매 거래량, 건설산업연구원 전망, "
        "대한건설협회 수주, 건설 수주액"
    )
    
    preset_pf = (
        "부동산 신탁 수주, 신탁계약 체결, 리츠 인가, PF 대출 보증, 시행사 시공사 선정, 재개발 수주, "
        "부동산 PF 조달, 브릿지론 본PF 전환, 그린리모델링 사업"
    )

    preset_policy = (
        "주택 공급 대책, 노후계획도시 특별법, 재건축 규제 완화, 부동산 PF 지원, 그린벨트 해제, "
        "공공분양 뉴홈, 다주택자 규제, 수도권 규제, 투기과열지구, 대출 규제, 전월세"
    )

    if 'search_keywords' not in st.session_state: st.session_state['search_keywords'] = preset_hotel
    st.sidebar.subheader("⚡ 키워드 자동 완성")
    
    c1, c2 = st.sidebar.columns(2)
    with c1:
        if st.button("🏨 호텔/리조트"): st.session_state['search_keywords'] = preset_hotel
        if st.button("🏗️ 건자재/수주"): st.session_state['search_keywords'] = preset_market
        if st.button("💰 PF/신탁/금융"): st.session_state['search_keywords'] = preset_pf
    with c2:
        if st.button("🏢 오피스/사옥"): st.session_state['search_keywords'] = preset_office
        if st.button("📈 건설경기/통계"): st.session_state['search_keywords'] = preset_trend
        if st.button("🏛️ 정부 정책/규제"): st.session_state['search_keywords'] = preset_policy
    
    user_input = st.sidebar.text_area("검색 키워드 (쉼표로 구분)", key='search_keywords', height=100)
    keywords = [k.strip() for k in user_input.split(',') if k.strip()]
    
    period = st.sidebar.selectbox("기간", ["전체 보기", "최근 24시간", "최근 3일", "최근 1주일", "최근 1개월", "최근 3개월"])
    
    if st.button("🔄 뉴스 새로고침"): st.cache_data.clear()

    with st.spinner('뉴스 수집 중... (중복 필터 적용 완료)'):
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
        search_txt = st.text_input("회사명 또는 종목코드", placeholder="예: 현대리바트, 079430")
        final_corp = None; stock_code = None

        if search_txt:
            if search_txt.isdigit() and len(search_txt) >= 6:
                final_corp = search_txt; stock_code = search_txt
            else:
                try:
                    cdf = dart.corp_codes
                    matches = cdf[cdf['corp_name'].str.contains(search_txt, na=False)]
                    
                    if not matches.empty:
                        matches['is_listed'] = matches['stock_code'].apply(lambda x: 0 if x and str(x).strip() != '' else 1)
                        matches = matches.sort_values(by='is_listed')
                        
                        def format_name(row):
                            code = row['stock_code']
                            if code and str(code).strip(): return f"{row['corp_name']} ({code})"
                            else: return f"{row['corp_name']} (기타법인)"
                        
                        matches['display_name'] = matches.apply(format_name, axis=1)
                        
                        sl = matches['display_name'].tolist()[:50]
                        sn = st.selectbox(f"검색 결과 ({len(matches)}개)", sl)
                        
                        selected_row = matches[matches['display_name'] == sn].iloc[0]
                        final_corp = selected_row['corp_code']
                        stock_code = selected_row['stock_code'] if selected_row['stock_code'] and str(selected_row['stock_code']).strip() else None
                        
                        st.session_state['dn'] = selected_row['corp_name']
                    else:
                        st.warning("목록에 없음")
                        if st.checkbox("강제 조회"): final_corp = search_txt; st.session_state['dn'] = search_txt
                except: final_corp = search_txt; st.session_state['dn'] = search_txt

        if st.button("🚀 분석 시작"):
            st.session_state['act'] = True; st.session_state['cp'] = final_corp; st.session_state['sc'] = stock_code

        if st.session_state.get('act'):
            tgt = st.session_state.get('cp'); sc = st.session_state.get('sc'); dn = st.session_state.get('dn', tgt)
            
            if sc:
                st.divider(); st.subheader(f"📈 {dn} 주가")
                res = get_stock_chart(dn, sc)
                if res:
                    f, l, c = res; st.metric("현재가", f"{l:,}원", f"{c:.2f}%")
                    st.plotly_chart(f, use_container_width=True)
                else: st.info("주가 정보 없음")
            else: st.divider(); st.info(f"📌 {dn} (비상장/기타법인)")

            st.divider(); st.subheader("💰 재무 성적표")
            sm = get_financial_summary_advanced(dart, tgt)
            if sm:
                st.markdown(f"**📌 {sm['title']}** (전년 대비)")
                
                # [NEW] AI 한줄평 출력
                st.success(f"💬 **[AI 영업맨 한줄평]** {sm['한줄평']}")
                
                c1,c2,c3 = st.columns(3)
                c1.metric("매출(누적)", sm['매출'][0], sm['매출'][1]); c1.caption(f"작년: {sm['매출'][2]}")
                c2.metric("영업이익", sm['영업'][0], sm['영업'][1]); c2.caption(f"이익률: {sm['영업이익률']}")
                c3.metric("순이익", sm['순익'][0], sm['순익'][1]); c3.caption(f"작년: {sm['순익'][2]}")
                
                st.markdown("---")
                
                # [NEW] 현금흐름 & 유동비율 추가
                k1, k2, k3 = st.columns(3)
                k1.metric("영업활동현금흐름 (돈맥)", sm['현금흐름'], help="영업으로 실제 벌어들인 현금 (+면 좋음)")
                k2.metric("유동비율 (지급능력)", sm['유동비율'], help="100% 이상이면 단기 부채 상환 능력 양호")
                k3.metric("부채비율 (안정성)", sm['부채비율'], help="200% 이하면 양호")
                
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
