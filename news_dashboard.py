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
import time
import io

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
        
        .date-badge {
            font-size: 1.2rem;
            font-weight: bold;
            color: #d32f2f; 
            background-color: #ffebee;
            padding: 5px 10px;
            border-radius: 5px;
            margin-bottom: 10px;
            display: inline-block;
        }

        a { text-decoration: none; color: #0068c9; font-weight: bold; }
        a:hover { text-decoration: underline; }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# [중요] API 키 설정 (여기 니 키를 넣어야 된다!)
# ---------------------------------------------------------
# 아래 키가 안 되면 DART 홈페이지에서 새로 발급받아서 바꿔라!
DART_API_KEY = "3522c934d5547db5cba3f51f8d832e1a82ebce55" 

# ---------------------------------------------------------
# 2. 사이드바
# ---------------------------------------------------------
try: st.sidebar.image("logo.png", use_column_width=True)
except: pass

st.sidebar.header("🛠️ 설정")
mode = st.sidebar.radio("모드 선택", 
    ["📰 뉴스 모니터링", "🏢 기업 공시 & 재무제표", "🏗️ 수주/계약 현황 (Lead)", "🏛️ 신탁/시행사 발굴 (Early Bird)"]
)

# ---------------------------------------------------------
# 3. 공통 함수 & 시스템 함수
# ---------------------------------------------------------
def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)[:150] + "..." 

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
                'keyword': term, 'title': raw_title, 'link': entry.link,
                'published': pub_date, 'summary': clean_html(entry.get('description', '')),
                'source': entry.get('source', {}).get('title', 'Google News')
            })
    return all_news

# [수정] 에러 메시지를 반환하도록 변경 (디버깅용)
@st.cache_resource
def get_dart_system():
    try:
        dart = OpenDartReader(DART_API_KEY) 
        return dart, None # 성공 시 에러 없음
    except Exception as e:
        return None, str(e) # 실패 시 에러 메시지 반환

# ---------------------------------------------------------
# (기존 함수들 생략 없이 유지 - 재무, 차트, 파싱 등)
# ---------------------------------------------------------
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
                                return tv, None, pv, "{:,} 억".format(int(tv/100000000))
                            except: continue
                    return None, None, None, "-"
                sn_val, _, _, sn_str = gv(['매출액', '수익(매출액)'])
                on_val, _, _, on_str = gv(['영업이익', '영업이익(손실)'])
                nn_val, _, _, nn_str = gv(['당기순이익', '당기순이익(손실)'])
                if sn_str == "-": continue
                assets_val, _, _, assets_str = gv(['자산총계'])
                liab_val, _, _, liab_str = gv(['부채총계'])
                equity_val, _, _, equity_str = gv(['자본총계'])
                curr_assets_val, _, _, _ = gv(['유동자산'])
                curr_liab_val, _, _, _ = gv(['유동부채'])
                ret_earn_val, _, _, ret_earn_str = gv(['이익잉여금', '미처분이익잉여금', '미처리결손금'])
                opm = 0; debt_ratio = 0; curr_ratio = 0
                if sn_val and sn_val != 0: opm = (on_val / sn_val) * 100
                if equity_val and equity_val != 0: debt_ratio = (liab_val / equity_val) * 100
                if curr_liab_val and curr_liab_val != 0: curr_ratio = (curr_assets_val / curr_liab_val) * 100
                
                # 심플한 분석 멘트
                analysis_lines = []
                if opm < 2: analysis_lines.append("📉 **[실적]** 마진율이 좀 짜다(2% 미만). 불경기 영향 받는갑다.")
                elif opm > 10: analysis_lines.append("🚀 **[실적]** 영업이익률 10% 넘네! 장사 억수로 잘한다.")
                else: analysis_lines.append("📊 **[실적]** 무난하게 장사하고 있다.")
                if debt_ratio > 200: analysis_lines.append("⚠️ **[재무]** 빚이 좀 많다(200% 초과). 조심해라.")
                else: analysis_lines.append("💰 **[재무]** 재무 상태는 안정적이다.")
                full_analysis = "\n\n".join(analysis_lines)

                rn = ""
                try:
                    rl = dart.list(corp_name, start=f"{year}-01-01", end=f"{year}-12-31", kind='A')
                    for i,r in rl.iterrows():
                        if c_name in r['report_nm']: rn = r['rcept_no']; break
                except: pass
                
                return {"title": f"{year}년 {c_name}", "매출": (sn_str, "", ""), "영업": (f"{on_str} ({opm:.1f}%)", "", ""), "순익": (nn_str, "", ""), "자산": assets_str, "부채비율": f"{debt_ratio:.1f}%", "이익잉여금": ret_earn_str, "유동비율": f"{curr_ratio:.1f}%", "분석내용": full_analysis, "link": rn}
            except: continue
    return None

def get_stock_chart(target, code, days):
    try:
        df = fdr.DataReader(code, datetime.now()-timedelta(days=days), datetime.now())
        if df.empty: return None, 0, 0
        l = df['Close'].iloc[-1]; p = df['Close'].iloc[-2]; c = ((l-p)/p)*100
        min_p = df['Close'].min(); max_p = df['Close'].max()
        margin = (max_p - min_p) * 0.1 if (max_p - min_p) > 0 else min_p * 0.05
        fig = px.area(df, x=df.index, y='Close')
        fig.update_layout(xaxis_title="", yaxis_title="", height=250, margin=dict(t=10,b=10,l=10,r=10), showlegend=False, yaxis_range=[min_p - margin, max_p + margin])
        fig.update_traces(line_color='#ff4b4b' if c>0 else '#4b4bff')
        return fig, l, c
    except: return None, 0, 0

def plot_advanced_chart(code, days, interval):
    try:
        df = fdr.DataReader(code, datetime.now()-timedelta(days=days), datetime.now())
        if df.empty: return None, 0, 0
        if interval == '주봉': df = df.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        elif interval == '월봉': df = df.resample('ME').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], increasing_line_color='#ff3b30', decreasing_line_color='#007aff')])
        fig.update_layout(xaxis_rangeslider_visible=False, height=250, margin=dict(t=10,b=10,l=10,r=10), yaxis_title="", showlegend=False)
        return fig, df['Close'].iloc[-1], ((df['Close'].iloc[-1]-df['Close'].iloc[-2])/df['Close'].iloc[-2])*100
    except: return None, 0, 0

def extract_contract_details(dart, rcp_no):
    contract_name = "-"; contract_amt = "-"; amt_val = 0; end_date = "-"; apt_desc = ""
    try:
        xml_text = dart.document(rcp_no)
        dong_match = re.search(r'(\d+)\s*개?\s*동', xml_text)
        if dong_match: apt_desc += f"{dong_match.group(1)}개동 "
        sede_match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*세대', xml_text)
        if sede_match: apt_desc += f"{sede_match.group(1)}세대"
        
        try: dfs = pd.read_html(io.StringIO(xml_text))
        except: dfs = []
        found_amt = False; found_date = False
        for df in dfs:
            df = df.fillna("")
            for idx, row in df.iterrows():
                row_str = " ".join(map(str, row.values))
                if contract_name == "-":
                    if "계약명" in row_str or "공사명" in row_str:
                        val = str(row.iloc[-1]).strip()
                        if val and val != "nan": contract_name = val
                if not found_amt:
                    if "계약금액" in row_str or "확정계약금액" in row_str:
                        raw_val = str(row.iloc[-1])
                        nums = re.findall(r'\d+', raw_val.replace(',',''))
                        if nums:
                            total_str = "".join(nums)
                            if len(total_str) > 8: amt_val = int(total_str); contract_amt = f"{amt_val / 100000000:,.1f} 억"; found_amt = True
                if not found_date:
                    if "계약기간" in row_str or "종료일" in row_str:
                        dates = re.findall(r'20\d{2}[-.]\d{2}[-.]\d{2}', str(row.iloc[-1]))
                        if dates: dates.sort(); end_date = dates[-1]; found_date = True
        
        if contract_amt == "-":
            amt_match = re.search(r'(계약금액|확정계약금액).*?</td>.*?<td.*?>(.*?)</td>', xml_text, re.DOTALL)
            if amt_match:
                nums = re.findall(r'\d+', re.sub('<.*?>', '', amt_match.group(2)).replace(',',''))
                if nums: amt_val = int("".join(nums)); contract_amt = f"{amt_val / 100000000:,.1f} 억"
        if end_date == "-":
            period_rows = re.findall(r'(계약기간|종료일).*?</tr>', xml_text, re.DOTALL)
            found_dates = []
            for row in period_rows: found_dates.extend(re.findall(r'20\d{2}[-.]\d{2}[-.]\d{2}', row))
            if found_dates: found_dates.sort(); end_date = found_dates[-1]
    except: pass
    return contract_name, contract_amt, amt_val, end_date, apt_desc

def extract_trust_details(dart, rcp_no):
    project_name = "-"; location = "-"
    try:
        xml_text = dart.document(rcp_no)
        proj_match = re.search(r'(사업명|신탁명칭|현장명).*?</td>.*?<td.*?>(.*?)</td>', xml_text, re.DOTALL)
        if proj_match: project_name = re.sub('<.*?>', '', proj_match.group(2)).strip()
        else:
            text_match = re.search(r'사업명\s*:\s*(.*?)(<br|\n)', xml_text)
            if text_match: project_name = re.sub('<.*?>', '', text_match.group(1)).strip()
        loc_match = re.search(r'(소재지|위치|대지위치).*?</td>.*?<td.*?>(.*?)</td>', xml_text, re.DOTALL)
        if loc_match: location = re.sub('<.*?>', '', loc_match.group(2)).strip()[:30] + "..."
    except: pass
    return project_name, location

# ---------------------------------------------------------
# [탭 1] 뉴스 모니터링
# ---------------------------------------------------------
if mode == "📰 뉴스 모니터링":
    st.title("💼 B2B 영업 인텔리전스")
    
    preset_market = "친환경 자재, 현대건설 수주, GS건설 수주, 디엘건설, 디엘이앤씨, 현대엔지니어링, 삼성물산 수주, 대우건설 수주, 세라믹 자재, 건설자재, 건자재, 컬러강판"
    
    user_input = st.sidebar.text_area("검색 키워드", value=preset_market, height=150)
    keywords = [k.strip() for k in user_input.split(',') if k.strip()]
    period = st.sidebar.radio("기간", ["최근 24시간", "최근 3일", "최근 1주일"], index=2)
    
    if st.button("뉴스 조회"):
        news = get_news(keywords)
        st.success(f"{len(news)}건 발견")
        for n in news:
            st.markdown(f"[{n['title']}]({n['link']}) - {n['published'].strftime('%m/%d')}")

# ---------------------------------------------------------
# [탭 2] 기업 공시 & 재무
# ---------------------------------------------------------
elif mode == "🏢 기업 공시 & 재무제표":
    st.title("🏢 기업 분석")
    # [수정] 에러 메시지 확인
    dart, err = get_dart_system()
    if dart is None:
        st.error(f"🚨 DART API 연결 실패! 에러 메시지를 확인하소:\n\n{err}")
        st.warning("👉 코드 맨 위에 `DART_API_KEY`가 올바른지 확인해라. 니 키가 없으면 DART 홈페이지에서 받아야 된데이!")
    else:
        search_txt = st.text_input("회사명", "현대리바트")
        if st.button("분석 시작"):
            corp_code = None
            try: 
                corp_code = dart.find_corp_code(search_txt)
            except: pass
            
            if not corp_code: st.error("회사를 못 찾겠데이. 이름 확인해라.")
            else:
                st.session_state['cp'] = corp_code
                st.session_state['act'] = True

        if st.session_state.get('act'):
            tgt = st.session_state.get('cp')
            sm = get_financial_summary_advanced(dart, tgt)
            if sm:
                st.info(sm['분석내용'])
                c1,c2,c3 = st.columns(3)
                c1.metric("매출", sm['매출'][0]); c2.metric("영업이익", sm['영업'][0]); c3.metric("순이익", sm['순익'][0])
            else: st.warning("재무 데이터가 없거나 로딩 실패했다.")

# ---------------------------------------------------------
# [탭 3] 수주 현황
# ---------------------------------------------------------
elif mode == "🏗️ 수주/계약 현황 (Lead)":
    st.title("🏗️ 수주 & 계약 현황")
    dart, err = get_dart_system()
    if dart is None: st.error(f"API 연결 실패: {err}")
    else:
        constructors = {"삼성물산": "028260", "현대건설": "000720", "GS건설": "006360", "대우건설": "047040", "DL이앤씨": "375500"}
        targets = st.multiselect("건설사", list(constructors.keys()), default=list(constructors.keys())[:2])
        if st.button("조회"):
            ed = datetime.now(); stt = ed - timedelta(days=90)
            for name in targets:
                try:
                    rpts = dart.list(constructors[name], start=stt.strftime('%Y-%m-%d'), end=ed.strftime('%Y-%m-%d'))
                    if rpts is not None:
                        leads = rpts[rpts['report_nm'].str.contains("단일판매|공급계약|수주")]
                        for i, r in leads.iterrows():
                            cn, ca, _, edate, apt = extract_contract_details(dart, r['rcept_no'])
                            with st.expander(f"{name} - {cn}"):
                                st.write(f"금액: {ca}, 종료: {edate}, 개요: {apt}")
                                st.link_button("원문", f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}")
                except: continue

# ---------------------------------------------------------
# [탭 4] 신탁사 발굴 (필터 강화)
# ---------------------------------------------------------
elif mode == "🏛️ 신탁/시행사 발굴 (Early Bird)":
    st.title("🏛️ 신탁사/시행사 발굴")
    dart, err = get_dart_system()
    if dart is None: st.error(f"API 연결 실패: {err}")
    else:
        trusts = {"한국토지신탁": "034830", "한국자산신탁": "123890", "KB부동산신탁": "KB부동산신탁", "하나자산신탁": "하나자산신탁"}
        targets = st.multiselect("신탁사", list(trusts.keys()), default=list(trusts.keys())[:2])
        
        c1, c2 = st.columns(2)
        date_opt = c1.radio("기간", ["최근 1개월", "최근 3개월", "최근 6개월"], index=1)
        search_query = c2.text_input("필터 (예: 대구, 오피스텔)", placeholder="특정 지역/용도만 검색")

        if st.button("신탁 사업 조회"):
            days_map = {"최근 1개월": 30, "최근 3개월": 90, "최근 6개월": 180}
            stt = (datetime.now() - timedelta(days=days_map[date_opt])).strftime('%Y-%m-%d')
            ed = datetime.now().strftime('%Y-%m-%d')
            
            prog = st.progress(0); status = st.empty(); idx = 0
            
            for name in targets:
                idx += 1; prog.progress(idx/len(targets)); status.text(f"{name} 검색 중...")
                try:
                    # [주의] 비상장사(KB, 하나 등)는 종목코드가 없어서 이름으로 검색 시도.
                    # 실패 시 Corp Code를 직접 찾아야 함. OpenDartReader는 이름 검색 지원함.
                    # 단, 이름이 정확해야 함. (주)하나자산신탁 등.
                    
                    rpts = dart.list(name, start=stt, end=ed) # 종목코드 대신 이름으로 검색 시도
                    if rpts is None or rpts.empty: continue
                    
                    mask = rpts['report_nm'].str.contains("신탁계약|정비사업|리츠|유형자산")
                    leads = rpts[mask]
                    
                    if search_query:
                        leads = leads[leads['report_nm'].str.contains(search_query)]
                    
                    leads = leads.head(5) # 속도 위해 5개 제한
                    
                    for i, r in leads.iterrows():
                        pn, loc = extract_trust_details(dart, r['rcept_no'])
                        disp = pn if pn != "-" else r['report_nm']
                        with st.expander(f"[{r['rcept_dt']}] {name} - {disp}"):
                            st.write(f"위치: {loc}")
                            st.link_button("원문", f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}")
                except Exception as e:
                    # 에러 발생 시 로그 출력 (사용자에게는 안 보임)
                    print(f"Error fetching {name}: {e}")
                    continue
            
            prog.empty(); status.empty()
            st.success("조회 완료! 결과가 없으면 기간을 늘리거나 필터를 지워보소.")
