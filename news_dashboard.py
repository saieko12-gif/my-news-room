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
# [디자인] 제목 안 잘리게 여백 조정 (3rem)
# ---------------------------------------------------------
st.markdown("""
    <style>
        .block-container { padding-top: 3rem; } 
        div[data-testid="column"] { padding: 0 !important; } 
        hr { margin: 0.3rem 0 !important; } 
        .stButton button { height: 2.5rem; padding-top: 0; padding-bottom: 0; } 
        
        /* [추가] 링크 텍스트 예쁘게 (파란색, 밑줄 없애고 마우스 올리면 밑줄) */
        a { text-decoration: none; color: #0068c9; font-weight: bold; }
        a:hover { text-decoration: underline; }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. 사이드바
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

# 재무제표 (누적 우선)
def get_financial_summary_advanced(dart, corp_name):
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
                    if target_fs.empty: target_fs = fs[fs['fs_div'] == 'OFS']

                    def get_data_pair(account_names):
                        for nm in account_names:
                            row = target_fs[target_fs['account_nm'] == nm]
                            if not row.empty:
                                try:
                                    this_val_str = row.iloc[0].get('thstrm_add_amount', row.iloc[0]['thstrm_amount'])
                                    if pd.isna(this_val_str) or this_val_str == '': this_val_str = row.iloc[0]['thstrm_amount']
                                    
                                    prev_val_str = row.iloc[0].get('frmtrm_add_amount', row.iloc[0]['frmtrm_amount'])
                                    if pd.isna(prev_val_str) or prev_val_str == '': prev_val_str = row.iloc[0]['frmtrm_amount']

                                    this_val = float(str(this_val_str).replace(',', ''))
                                    prev_val = 0 if (pd.isna(prev_val_str) or prev_val_str == '') else float(str(prev_val_str).replace(',', ''))

                                    this_view = "{:,} 억".format(int(this_val / 100000000))
                                    prev_view = "{:,} 억".format(int(prev_val / 100000000))
                                    
                                    delta = None
                                    if prev_val != 0:
                                        delta = f"{((this_val - prev_val) / prev_val) * 100:.1f}%"
                                    return this_view, delta, prev_view 
                                except: continue
                        return "-", None, "-"

                    sales_now, sales_delta, sales_prev = get_data_pair(['매출액', '수익(매출액)'])
                    if sales_now == "-": continue 
                    
                    op_now, op_delta, op_prev = get_data_pair(['영업이익', '영업이익(손실)'])
                    net_now, net_delta, net_prev = get_data_pair(['당기순이익', '당기순이익(손실)'])
                    
                    rcept_no = ""
                    try:
                        reports = dart.list(corp_name, start=f"{year}-01-01", end=f"{year}-12-31", kind='A')
                        keyword = "사업보고서" if code == '11011' else ("분기보고서" if code == '11014' else "반기보고서")
                        for idx, row in reports.iterrows():
                            if keyword in row['report_nm']:
                                rcept_no = row['rcept_no']
                                break
                    except: rcept_no = ""

                    return {
                        "title": f"{year}년 {code_name} (누적)",
                        "매출": (sales_now, sales_delta, sales_prev),
                        "영업이익": (op_now, op_delta, op_prev),
                        "순이익": (net_now, net_delta, net_prev),
                        "rcept_no": rcept_no 
                    }
            except: continue
    return None

# ---------------------------------------------------------
# [탭 1] 뉴스 모니터링
# ---------------------------------------------------------
if mode == "📰 뉴스 모니터링":
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
    
    user_input = st.sidebar.text_area("검색할 키워드", key='search_keywords', height=150)
    keywords = [k.strip() for k in user_input.split(',') if k.strip()]
    period_option = st.sidebar.selectbox("조회 기간", ["전체 보기", "최근 24시간", "최근 3일", "최근 1주일", "최근 1개월"])
    
    if st.button("🔄 최신 뉴스 다시 불러오기"): st.cache_data.clear()

    with st.spinner('뉴스 수집 중...'):
        news_list = get_news(keywords)
    news_list.sort(key=lambda x: x['published'], reverse=True)

    date_filtered = []
    now = datetime.now()
    if news_list:
        now = datetime.now(news_list[0]['published'].tzinfo) 
        for n in news_list:
            diff = now - n['published']
            if period_option == "최근 24시간" and diff > timedelta(hours=24): continue
            elif period_option == "최근 3일" and diff > timedelta(days=3): continue
            elif period_option == "최근 1주일" and diff > timedelta(days=7): continue
            elif period_option == "최근 1개월" and diff > timedelta(days=30): continue
            date_filtered.append(n)

    if not date_filtered: st.warning("조건에 맞는 뉴스가 없다!")
    else:
        st.divider()
        st.subheader("📊 키워드 트렌드")
        df = pd.DataFrame(date_filtered)
        if not df.empty:
            cnt = df['keyword'].value_counts().reset_index()
            cnt.columns = ['키워드', '개수']
            fig = px.bar(cnt, x='개수', y='키워드', orientation='h', text='개수', color='개수', color_continuous_scale='Teal')
            fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', xaxis_title="", yaxis_title="", height=250, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader(f"🔎 뉴스 상세 ({len(date_filtered)}건)")
        c1, c2 = st.columns([1, 2])
        search_q = c1.text_input("제목 검색")
        found_keys = list(set([n['keyword'] for n in date_filtered]))
        sel_keys = c2.multiselect("키워드 필터", found_keys, found_keys)
        
        final = [n for n in date_filtered if n['keyword'] in sel_keys and (not search_q or search_q in n['title'])]
        
        for n in final:
            s_date = n['published'].strftime("%m/%d")
            f_date = n['published'].strftime("%Y-%m-%d %H:%M")
            with st.expander(f"({s_date}) [{n['keyword']}] {n['title']}"):
                if n['summary']: st.info(n['summary'])
                st.write(f"**출처:** {n['source']} | {f_date}")
                st.link_button("원문 보기", n['link'])

# ---------------------------------------------------------
# [탭 2] 기업 공시 & 재무제표 (여기가 바뀜! 텍스트 링크!)
# ---------------------------------------------------------
elif mode == "🏢 기업 공시 & 재무제표":
    st.subheader("🏢 기업 분석 (공시 + 재무성장률)")
    
    dart = get_dart_system()
    if dart is None: st.error("API 키 확인 필요")
    else:
        search_text = st.text_input("회사명/종목코드", placeholder="예: 현대건설, 000720")
        final_corp = None 
        
        if search_text:
            if search_text.isdigit() and len(search_text) >= 6:
                final_corp = search_text 
                st.info(f"🔢 종목코드 **'{search_text}'** 조회")
            else:
                try:
                    candidates = dart.corp_codes[dart.corp_codes['corp_name'].str.contains(search_text)]
                    if not candidates.empty:
                        final_corp = st.selectbox(f"검색 결과 ({len(candidates)}개)", candidates['corp_name'].tolist())
                    else:
                        st.warning(f"목록에 없음.")
                        if st.checkbox(f"✅ '{search_text}' 강제 조회"): final_corp = search_text
                except: final_corp = search_text
        
        if final_corp:
            if st.button("🚀 분석 시작"):
                # A. 재무제표
                st.divider()
                st.subheader(f"📈 '{final_corp}' 재무 성적표")
                with st.spinner("누적 실적 계산 중..."):
                    summ = get_financial_summary_advanced(dart, final_corp)
                    if summ:
                        st.markdown(f"**📌 기준: {summ['title']}** (전년 대비)")
                        c1, c2, c3 = st.columns(3)
                        
                        s_n, s_d, s_p = summ['매출']
                        o_n, o_d, o_p = summ['영업이익']
                        n_n, n_d, n_p = summ['순이익']
                        
                        c1.metric("매출 (누적)", s_n, s_d); c1.caption(f"작년: {s_p}")
                        c2.metric("영업이익 (누적)", o_n, o_d); c2.caption(f"작년: {o_p}")
                        c3.metric("순이익 (누적)", n_n, n_d); c3.caption(f"작년: {n_p}")
                        
                        if summ['rcept_no']:
                            st.link_button("📄 데이터 출처(보고서) 보기", f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={summ['rcept_no']}")
                    else: st.warning("재무 정보 없음")

                # B. 공시 리스트 (텍스트 링크 적용)
                st.divider()
                st.subheader("📋 공시 리스트")
                
                with st.spinner("공시 로딩 중..."):
                    try:
                        end = datetime.now()
                        start = end - timedelta(days=365)
                        reports = dart.list(final_corp, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))
                        
                        if reports is None or reports.empty:
                            st.error("공시 내역 없음")
                        else:
                            filter_query = st.text_input("🔍 공시 결과 내 검색 (예: 수주, 계약, 증자...)", placeholder="찾고 싶은 단어 입력...")
                            
                            if filter_query:
                                reports = reports[reports['report_nm'].str.contains(filter_query)]
                                st.success(f"검색 결과: **{len(reports)}건**")
                            
                            # [레이아웃 수정] 버튼 칸 없애고, 제목 칸을 넓혔다!
                            h1, h2 = st.columns([1.5, 8.5])
                            h1.markdown("**날짜**")
                            h2.markdown("**공시 제목 (제출인)**")
                            st.markdown("---")

                            for idx, row in reports.iterrows():
                                title = row['report_nm']
                                link = f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={row['rcept_no']}"
                                date_str = row['rcept_dt']
                                f_date = f"{date_str[2:4]}/{date_str[4:6]}/{date_str[6:]}" 
                                submitter = row['flr_nm']

                                c1, c2 = st.columns([1.5, 8.5])
                                c1.text(f_date)
                                
                                # [핵심] Markdown 링크 문법 사용 [제목](링크)
                                # unsafe_allow_html=True를 써서 제출인은 회색으로 작게 처리함
                                c2.markdown(f"[{title}]({link}) <span style='color:grey; font-size:0.8em'>({submitter})</span>", unsafe_allow_html=True)
                                
                                st.markdown("<hr style='margin: 3px 0; border-top: 1px solid #eee;'>", unsafe_allow_html=True)

                    except Exception as e: st.error(f"에러: {e}")
