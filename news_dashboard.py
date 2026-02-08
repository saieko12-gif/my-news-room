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
        
        /* 날짜 강조 스타일 */
        .date-badge {
            font-size: 1.2rem;
            font-weight: bold;
            color: #d32f2f; /* 빨간색 */
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

# [중요] API 키
DART_API_KEY = "3522c934d5547db5cba3f51f8d832e1a82ebce55"

# ---------------------------------------------------------
# 2. 사이드바
# ---------------------------------------------------------
try: st.sidebar.image("logo.png", use_column_width=True)
except: pass

st.sidebar.header("🛠️ 설정")
mode = st.sidebar.radio("모드 선택", ["📰 뉴스 모니터링", "🏢 기업 공시 & 재무제표", "🏗️ 수주/계약 현황 (Lead)"])

# ---------------------------------------------------------
# 3. 공통 함수
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

# 재무제표 분석 함수
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

                sn_val, sd, sp_val, sn_str = gv(['매출액', '수익(매출액)'])
                on_val, od, op_val, on_str = gv(['영업이익', '영업이익(손실)'])
                nn_val, nd, np_val, nn_str = gv(['당기순이익', '당기순이익(손실)'])
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
                
                rev_growth = float(sd.replace('%', '')) if sd else 0
                on_display = f"{on_str} ({opm:.1f}%)"

                analysis_lines = []
                if rev_growth < -5 or opm < 2:
                    perf_msg = f"📉 **[실적]** 요새 경기가 얼어붙어가 매출({sd if sd else '0%'})이랑 이익이 쪼그라들었네. 불경기 직격탄 맞았다."
                elif rev_growth > 5 and opm > 5:
                    perf_msg = f"🚀 **[실적]** 매출도 {sd} 뛰고 이익률도 {opm:.1f}%나 찍었다. 장사 억수로 잘했네!"
                elif rev_growth > 0:
                    perf_msg = f"📊 **[실적]** 매출은 쪼매 늘었는데({sd}), 시장 상황 대비 선방했다."
                else:
                    perf_msg = f"📉 **[실적]** 매출이 {sd} 빠져서 성장이 정체됐네."
                analysis_lines.append(perf_msg)

                if debt_ratio < 100 and ret_earn_val and ret_earn_val > 0:
                    health_msg = f"💰 **[재무]** 근데 걱정 마라. 빚(부채비율 {debt_ratio:.0f}%)도 거의 없고, 곳간(잉여금 {ret_earn_str})이 꽉 차가 **기초체력은 국대급**이다."
                elif debt_ratio > 200:
                    health_msg = f"⚠️ **[재무]** 근데 빚이 좀 많다(부채비율 {debt_ratio:.0f}%). 재무구조가 불안하니 조심해야 된데이."
                else:
                    health_msg = f"💰 **[재무]** 부채비율 {debt_ratio:.0f}% 수준으로 재무 상태는 무난~하다."
                analysis_lines.append(health_msg)

                if (rev_growth < 0 or opm < 2) and (debt_ratio < 100):
                    strat_msg = "🚀 **[전략]** 당장 실적은 아쉬워도 맷집 좋은 우량 고객이다. **망할 걱정 말고 길게 보고 거래 터라!**"
                elif debt_ratio > 200:
                    strat_msg = "🛑 **[전략]** 실속도 없고 빚도 많다. **외상 거래는 절대 금물!** 무조건 선결제 받아라."
                elif rev_growth > 5 and opm > 5:
                    strat_msg = "🔥 **[전략]** 지금 물 들어왔다! **적극적으로 영업해서 물량 늘려라!**"
                else:
                    strat_msg = "✅ **[전략]** 크게 무리 없는 회사다. 꾸준히 관계 유지하모 되겠다."
                analysis_lines.append(strat_msg)

                full_analysis = "\n\n".join(analysis_lines)

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
                    "영업": (on_display, od, "{:,} 억".format(int(op_val/100000000)) if op_val else "-"), 
                    "순익": (nn_str, nd, "{:,} 억".format(int(np_val/100000000)) if np_val else "-"),
                    "자산": assets_str,
                    "부채비율": f"{debt_ratio:.1f}%",
                    "이익잉여금": ret_earn_str,
                    "유동비율": f"{curr_ratio:.1f}%",
                    "분석내용": full_analysis,
                    "link": rn
                }
            except: continue
    return None

# [변경] 영역 차트: Y축 범위 자동 조정 (변동성 확대) & 높이 축소
def get_stock_chart(target, code, days):
    try:
        df = fdr.DataReader(code, datetime.now()-timedelta(days=days), datetime.now())
        if df.empty: return None
        l = df['Close'].iloc[-1]; p = df['Close'].iloc[-2]; c = ((l-p)/p)*100
        clr = '#ff4b4b' if c>0 else '#4b4bff'
        
        # [NEW] Y축 범위 동적 계산 (최저/최고가 기준 + 5% 여유)
        min_p = df['Close'].min()
        max_p = df['Close'].max()
        margin = (max_p - min_p) * 0.1 # 10% 여유
        if margin == 0: margin = min_p * 0.05 # 일직선일 경우 예외처리

        fig = px.area(df, x=df.index, y='Close')
        
        # [NEW] update_layout에서 높이 250으로 축소, yaxis_range 설정
        fig.update_layout(
            xaxis_title="", 
            yaxis_title="", 
            height=250, # 높이 축소 (기존 350)
            margin=dict(t=10,b=10,l=10,r=10), 
            showlegend=False,
            yaxis_range=[min_p - margin, max_p + margin] # 0원부터 시작 안 함
        )
        fig.update_traces(line_color=clr)
        return fig, l, c
    except: return None

# [변경] 캔들 차트: 높이 축소
def plot_advanced_chart(code, days, interval):
    try:
        start_date = datetime.now() - timedelta(days=days)
        df = fdr.DataReader(code, start_date, datetime.now())
        
        if df.empty: return None

        if interval == '주봉':
            df = df.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        elif interval == '월봉':
            df = df.resample('ME').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'})
        
        fig = go.Figure(data=[go.Candlestick(x=df.index,
                        open=df['Open'], high=df['High'],
                        low=df['Low'], close=df['Close'],
                        increasing_line_color='#ff3b30',
                        decreasing_line_color='#007aff'
                        )])

        fig.update_layout(
            xaxis_rangeslider_visible=False,
            height=250, # 높이 축소
            margin=dict(t=10,b=10,l=10,r=10),
            yaxis_title="주가 (원)",
            showlegend=False
        )
        
        last_val = df['Close'].iloc[-1]
        prev_val = df['Close'].iloc[-2]
        chg = ((last_val - prev_val) / prev_val) * 100
        
        return fig, last_val, chg
    except Exception as e:
        return None, 0, 0

# [핵심 변경] 기재정정 완벽 파싱 + 아파트 세대수 추출
def extract_contract_details(dart, rcp_no):
    try:
        xml_text = dart.document(rcp_no)
        
        # 1. 계약명
        nm_match = re.search(r'(계약명|공사명|계약의 명칭).*?</td>.*?<td.*?>(.*?)</td>', xml_text, re.DOTALL)
        contract_name = "-"
        if nm_match:
            contract_name = re.sub('<.*?>', '', nm_match.group(2)).strip()
        
        # 2. 계약금액
        amt_match = re.search(r'(계약금액|확정계약금액).*?</td>.*?<td.*?>(.*?)</td>', xml_text, re.DOTALL)
        contract_amt = "-"
        amt_val = 0
        if amt_match:
            raw_amt_clean = re.sub('<.*?>', '', amt_match.group(2)).replace(',','').strip()
            nums = re.findall(r'\d+', raw_amt_clean)
            if nums:
                amt_val = int("".join(nums))
                contract_amt = f"{amt_val / 100000000:,.1f} 억"

        # 3. [UPGRADE] 계약기간 (기재정정 대응: 날짜 여러 개면 가장 늦은 날짜 추출)
        end_date = "-"
        
        # 날짜 패턴 (YYYY-MM-DD 또는 YYYY.MM.DD)
        date_pattern = r'20\d{2}[-.]\d{2}[-.]\d{2}'
        
        # "종료일" or "계약기간" 키워드가 있는 행을 찾음
        period_rows = re.findall(r'(계약기간|종료일|공사기간).*?</tr>', xml_text, re.DOTALL)
        
        found_dates = []
        for row in period_rows:
            # 해당 행에 있는 모든 날짜 추출
            dates = re.findall(date_pattern, row)
            found_dates.extend(dates)
            
        if found_dates:
            # 추출된 날짜 중 가장 늦은 날짜를 종료일로 간주 (정정 후 날짜일 확률 높음)
            found_dates.sort()
            end_date = found_dates[-1]

        # 4. [NEW] 아파트 규모 (동수, 세대수) 추출
        apt_info = []
        # "개동" 추출 (예: 8개동, 8 개동)
        dong_match = re.search(r'(\d+)\s*개?\s*동', xml_text)
        if dong_match:
            apt_info.append(f"{dong_match.group(1)}개동")
            
        # "세대" 추출 (예: 722세대, 1,000 세대)
        sede_match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*세대', xml_text)
        if sede_match:
            apt_info.append(f"{sede_match.group(1)}세대")
            
        apt_desc = ", ".join(apt_info) if apt_info else ""

        return contract_name, contract_amt, amt_val, end_date, apt_desc
    except:
        return "-", "-", 0, "-", ""

# ---------------------------------------------------------
# [탭 1] 뉴스 모니터링
# ---------------------------------------------------------
if mode == "📰 뉴스 모니터링":
    st.title("💼 B2B 영업 인텔리전스")
    st.markdown("뉴스, 공시, 재무, 그리고 **주가 흐름**까지! **스마트한 영업맨의 비밀무기**")
    
    preset_hotel = "호텔 리모델링, 신규 호텔 오픈, 리조트 착공, 5성급 호텔 리뉴얼, 호텔 FF&E, 생활숙박시설 분양, 호텔 매각, 샌즈"
    preset_office = "사옥 이전, 통합 사옥 건립, 스마트 오피스, 기업 연수원 건립, 공공청사 리모델링, 공유 오피스 출점, 오피스 인테리어, 데이터센터"
    preset_market = "친환경 자재, 현대건설 수주, GS건설 수주, 디엘건설, 디엘이앤씨, 현대엔지니어링, 삼성물산 수주, 대우건설 수주, 세라믹 자재, 건설자재, 건자재, 컬러강판"
    preset_trend = "미분양 주택, 미분양 현황, 아파트 입주 물량, 주택 준공 실적, 건축허가 면적, 아파트 매매 거래량, 건설산업연구원 전망, 대한건설협회 수주, 건설 수주액"
    preset_pf = "부동산 신탁 수주, 신탁계약 체결, 리츠 인가, PF 대출 보증, 시행사 시공사 선정, 재개발 수주, 부동산 PF 조달, 브릿지론 본PF 전환, 그린리모델링 사업"
    preset_policy = "주택 공급 대책, 노후계획도시 특별법, 재건축 규제 완화, 부동산 PF 지원, 그린벨트 해제, 공공분양 뉴홈, 다주택자 규제, 수도권 규제, 투기과열지구, 대출 규제, 전월세"

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
    
    user_input = st.sidebar.text_area("검색 키워드 (쉼표로 구분)", key='search_keywords', height=250)
    keywords = [k.strip() for k in user_input.split(',') if k.strip()]
    
    period = st.sidebar.radio(
        "기간 선택", 
        ["최근 24시간", "최근 3일", "최근 1주일", "최근 1개월", "최근 3개월", "전체 보기"], 
        index=2
    )
    
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
# [탭 2] 기업 공시 & 재무제표 (차트 옵션 통합)
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
                st.divider(); st.subheader(f"📈 {dn} 주가 차트")
                
                chart_opt = st.radio(
                    "차트 옵션",
                    ["일봉", "주봉", "월봉", "1개월", "3개월", "1년", "3년"],
                    horizontal=True,
                    index=5
                )
                
                fig = None; l = 0; c = 0

                if chart_opt in ["일봉", "주봉", "월봉"]:
                    if chart_opt == "일봉":
                        days = 60 
                        interval = "일봉"
                    elif chart_opt == "주봉":
                        days = 365 
                        interval = "주봉"
                    else: 
                        days = 1095 
                        interval = "월봉"
                    fig, l, c = plot_advanced_chart(sc, days, interval)
                
                else:
                    days_map = {"1개월": 30, "3개월": 90, "1년": 365, "3년": 1095}
                    days = days_map[chart_opt]
                    fig, l, c = get_stock_chart(dn, sc, days)

                if fig:
                    st.metric("현재가", f"{l:,}원", f"{c:.2f}%")
                    st.plotly_chart(fig, use_container_width=True)
                else: st.info("주가 정보 없음")
            else: st.divider(); st.info(f"📌 {dn} (비상장/기타법인)")

            st.divider(); st.subheader("💰 재무 성적표")
            sm = get_financial_summary_advanced(dart, tgt)
            if sm:
                st.info(f"💡 **[AI 영업맨 심층 분석]**\n\n{sm['분석내용']}")
                st.markdown(f'<div class="date-badge">📅 기준: {sm["title"]} (전년 동기 대비)</div>', unsafe_allow_html=True)
                
                c1,c2,c3 = st.columns(3)
                c1.metric("매출(누적)", sm['매출'][0], sm['매출'][1]); c1.caption(f"작년: {sm['매출'][2]}")
                c2.metric("영업이익 (이익률)", sm['영업'][0], sm['영업'][1]); c2.caption(f"작년: {sm['영업'][2]}") 
                c3.metric("순이익", sm['순익'][0], sm['순익'][1]); c3.caption(f"작년: {sm['순익'][2]}")
                
                st.markdown("---")
                k1, k2, k3 = st.columns(3)
                k1.metric("이익잉여금 (비상금)", sm['이익잉여금'], help="회사가 쌓아둔 현금성 자본 (많을수록 안전)")
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

# ---------------------------------------------------------
# [탭 3] 수주/계약 현황
# ---------------------------------------------------------
elif mode == "🏗️ 수주/계약 현황 (Lead)":
    st.title("🏗️ 수주 & 계약 현황 (영업 Lead 발굴)")
    st.markdown("건설사들의 **'계약 종료일(준공 예정일)'**을 확인하고 **영업 타이밍**을 잡으소!")

    dart = get_dart_system()
    if dart is None: st.error("API 연결 실패")
    else:
        constructors = {
            "1위 삼성물산": "028260", "2위 현대건설": "000720", "3위 대우건설": "047040",
            "4위 현대엔지니어링": "현대엔지니어링", "5위 DL이앤씨": "375500", "6위 GS건설": "006360",
            "7위 포스코이앤씨": "포스코이앤씨", "8위 롯데건설": "롯데건설", "9위 SK에코플랜트": "SK에코플랜트",
            "10위 HDC현대산업개발": "294870"
        }
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("##### 👷 분석할 건설사 선택")
            target_corps_keys = st.multiselect(
                "체크박스에서 건설사를 선택하소 (기본: 전체 선택)",
                options=list(constructors.keys()),
                default=list(constructors.keys())
            )
        
        with col2:
            st.markdown("##### 📅 검색 기간")
            date_opt = st.radio("기간 선택", ["최근 1년", "전체 기간(3년)"])
            
        with st.expander("➕ 다른 회사 직접 검색하기 (직접 입력)"):
            custom_input = st.text_input("회사명 입력 (쉼표로 구분)", placeholder="예: 태영건설, 코오롱글로벌")
        
        final_targets = {}
        for k in target_corps_keys:
            final_targets[k] = constructors[k]
            
        if custom_input:
            for c in custom_input.split(','):
                name = c.strip()
                if name: final_targets[name] = name

        if st.button("🔍 수주 현장 정밀 분석"):
            st.divider()
            
            ed = datetime.now()
            days_back = 365 if date_opt == "최근 1년" else 1095
            stt = ed - timedelta(days=days_back)
            
            all_leads = []
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            total_targets = len(final_targets)
            current_idx = 0

            for name, code in final_targets.items():
                current_idx += 1
                status_text.text(f"🚧 {name} 공시 털어오는 중... ({current_idx}/{total_targets})")
                progress_bar.progress(current_idx / total_targets)
                
                try:
                    rpts = dart.list(code, start=stt.strftime('%Y-%m-%d'), end=ed.strftime('%Y-%m-%d'))
                    if rpts is None or rpts.empty: continue
                    
                    mask = rpts['report_nm'].str.contains("단일판매|공급계약|수주")
                    leads = rpts[mask]
                    leads = leads.head(10)
                    
                    for i, r in leads.iterrows():
                        # [UPGRADE] 날짜 정밀 파싱 + 아파트 규모 추출
                        c_name, c_amt, c_val, c_end, c_apt = extract_contract_details(dart, r['rcept_no'])
                        display_name = c_name if c_name != "-" else r['report_nm']
                        
                        all_leads.append({
                            "날짜": r['rcept_dt'],
                            "건설사": name.split(' ')[1] if '위' in name else name,
                            "계약명 (현장)": display_name,
                            "계약금액": c_amt,
                            "준공예정일 (종료일)": c_end,
                            "규모 (공사개요)": c_apt, # [NEW]
                            "금액(숫자)": c_val,
                            "공시제목": r['report_nm'],
                            "링크": f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}"
                        })
                except: continue
            
            progress_bar.empty()
            status_text.empty()

            if not all_leads:
                st.warning("조건에 맞는 수주 공시가 없데이.")
            else:
                df = pd.DataFrame(all_leads)
                df = df.sort_values(by="날짜", ascending=False)
                
                c1, c2 = st.columns([8, 2])
                c1.success(f"총 {len(df)}건의 알짜배기 현장 발견! (최근 순)")
                
                with c2:
                    csv = df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="💾 엑셀(CSV) 다운로드",
                        data=csv,
                        file_name='construction_leads.csv',
                        mime='text/csv',
                    )
                
                for i, row in df.iterrows():
                    dt = row['날짜']
                    fmt_dt = f"{dt[0:4]}-{dt[4:6]}-{dt[6:8]}"
                    
                    with st.expander(f"[{fmt_dt}] {row['건설사']} - {row['계약명 (현장)']}"):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.markdown(f"**🏗️ 현장명:** {row['계약명 (현장)']}")
                            st.markdown(f"**💵 계약금액:** :red[**{row['계약금액']}**]")
                            st.markdown(f"**🗓️ 준공예정(종료일):** **{row['준공예정일 (종료일)']}**")
                            # [NEW] 아파트 규모 표시
                            if row['규모 (공사개요)']:
                                st.markdown(f"**🏢 공사개요:** {row['규모 (공사개요)']}")
                            st.caption(f"공시제목: {row['공시제목']}")
                        with c2:
                            st.link_button("📄 원문 보기", row['링크'])
