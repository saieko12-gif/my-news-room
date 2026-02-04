import ssl
import time
import feedparser
from datetime import datetime, timedelta
from urllib.parse import quote

import streamlit as st

# 회사 SSL 인증서 문제 우회 (필수 설정)
ssl._create_default_https_context = ssl._create_unverified_context

# -----------------------------
# 설정: 키워드 목록
# -----------------------------
CORE_SALES_KEYWORDS = [
    "호텔 리모델링",
    "건자재 가격",
    "건설업 전망",
]

ORDER_OPPORTUNITY_KEYWORDS = [
    "신규 리조트 분양",
    "재건축 인테리어",
    "오피스 리모델링",
]

INDUSTRY_TREND_KEYWORDS = [
    "한샘 B2B",
    "LX하우시스",
    "현대리바트",
]

ALL_KEYWORDS = (
    CORE_SALES_KEYWORDS
    + ORDER_OPPORTUNITY_KEYWORDS
    + INDUSTRY_TREND_KEYWORDS
)


# -----------------------------
# 유틸 함수
# -----------------------------
def build_google_news_rss_url(keyword: str) -> str:
    base = "https://news.google.com/rss/search"
    query = quote(keyword)
    # 한국어/한국 기준
    return f"{base}?q={query}&hl=ko&gl=KR&ceid=KR:ko"


def get_published_datetime(entry):
    """RSS 엔트리에서 datetime 객체 추출."""
    # feedparser가 제공하는 시간 정보 활용
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6])

    # published 문자열이 있을 경우, dateutil이 있으면 활용
    if hasattr(entry, "published"):
        published_str = getattr(entry, "published", None)
        if published_str:
            try:
                from dateutil import parser as dateutil_parser  # type: ignore

                return dateutil_parser.parse(published_str)
            except Exception:
                # dateutil 미설치 또는 파싱 실패 시 무시
                pass

    return None


def format_datetime_kr(dt: datetime | None) -> str:
    """한국형 표시: 2024-02-05 (월) 14:30"""
    if dt is None:
        return "날짜 정보 없음"

    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    weekday_kr = weekdays[dt.weekday()]
    return dt.strftime(f"%Y-%m-%d ({weekday_kr}) %H:%M")


def extract_source(entry) -> str:
    # 1) entry.source.title 형태
    try:
        source = getattr(getattr(entry, "source", None), "title", None)
        if source:
            return source
    except Exception:
        pass

    # 2) dict 형태
    src = getattr(entry, "source", None)
    if isinstance(src, dict):
        if "title" in src:
            return src["title"]

    # 3) 제목에서 "- 언론사명" 패턴 추출
    title = getattr(entry, "title", "")
    if " - " in title:
        return title.split(" - ")[-1].strip()

    return "출처 미상"


# -----------------------------
# 데이터 가져오기 (캐시)
# -----------------------------
@st.cache_data(show_spinner="뉴스를 불러오는 중입니다...")
def fetch_news_for_keyword(keyword: str, refresh_token: float):
    """키워드별 뉴스 목록 가져오기 (refresh_token으로 강제 갱신)."""
    url = build_google_news_rss_url(keyword)
    feed = feedparser.parse(url)

    news_list = []
    for entry in feed.entries:
        dt = get_published_datetime(entry)
        news_list.append(
            {
                "title": getattr(entry, "title", "제목 없음"),
                "link": getattr(entry, "link", "#"),
                "published_dt": dt,
                "published_display": format_datetime_kr(dt),
                "source": extract_source(entry),
                "summary": getattr(entry, "summary", ""),
            }
        )
    return news_list


@st.cache_data(show_spinner=False)
def fetch_all_news(keywords, refresh_token: float):
    """여러 키워드에 대해 한 번에 뉴스 가져오기."""
    result = {}
    for kw in keywords:
        result[kw] = fetch_news_for_keyword(kw, refresh_token)
    return result


def filter_news_by_period(items, period_label: str):
    """조회 기간 라벨에 따라 뉴스 목록 필터링."""
    if period_label == "전체 보기":
        return items

    now = datetime.now()

    if period_label == "최근 24시간":
        threshold = now - timedelta(days=1)
    elif period_label == "최근 1주일":
        threshold = now - timedelta(days=7)
    elif period_label == "최근 1개월":
        threshold = now - timedelta(days=30)
    else:
        return items

    return [
        item
        for item in items
        if item.get("published_dt") is not None
        and item["published_dt"] >= threshold
    ]


# -----------------------------
# Streamlit UI
# -----------------------------
def main():
    st.set_page_config(
        page_title="B2B 영업용 뉴스 자동 수집기",
        layout="wide",
    )

    st.title("📊 B2B 영업용 뉴스 자동 수집기")
    st.caption("구글 뉴스 RSS + Streamlit 대시보드")

    # 세션 상태: 마지막 갱신 시간 (캐시 무효화를 위한 토큰)
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = time.time()

    # -------------------------
    # 사이드바 영역
    # -------------------------
    with st.sidebar:
        st.header("🔍 키워드 필터")

        period_label = st.selectbox(
            "조회 기간",
            ["전체 보기", "최근 24시간", "최근 1주일", "최근 1개월"],
            index=0,
        )

        keyword_filter_mode = st.radio(
            "조회 방식 선택",
            ["전체 보기", "단일 키워드 선택"],
            index=0,
        )

        selected_keyword = None
        if keyword_filter_mode == "단일 키워드 선택":
            selected_keyword = st.selectbox(
                "키워드 선택",
                ALL_KEYWORDS,
                index=0,
                help="관심 있는 키워드를 선택하세요.",
            )

        st.markdown("---")

        if st.button("🔄 데이터 갱신", use_container_width=True):
            # 캐시 무효화를 위해 토큰 변경
            st.session_state.last_refresh = time.time()
            st.success("최신 뉴스로 갱신했습니다.")

        st.markdown("#### 키워드 그룹")
        st.markdown("**핵심 영업**")
        for k in CORE_SALES_KEYWORDS:
            st.write(f"- {k}")

        st.markdown("**수주 기회**")
        for k in ORDER_OPPORTUNITY_KEYWORDS:
            st.write(f"- {k}")

        st.markdown("**업계 동향**")
        for k in INDUSTRY_TREND_KEYWORDS:
            st.write(f"- {k}")

    # -------------------------
    # 메인 콘텐츠: 뉴스 리스트
    # -------------------------
    st.subheader("📰 뉴스 리스트")

    # 뉴스 데이터 가져오기
    refresh_token = st.session_state.last_refresh

    if keyword_filter_mode == "전체 보기":
        raw_news_data = fetch_all_news(ALL_KEYWORDS, refresh_token)
    else:
        # 단일 키워드만 조회
        news_list = fetch_news_for_keyword(selected_keyword, refresh_token)
        raw_news_data = {selected_keyword: news_list}

    # 기간 필터 및 날짜순 정렬 적용
    news_data = {}
    for keyword, items in raw_news_data.items():
        filtered_items = filter_news_by_period(items, period_label)
        # 최신 뉴스가 위로 오도록 정렬
        filtered_items.sort(
            key=lambda x: x.get("published_dt") or datetime.min,
            reverse=True,
        )
        news_data[keyword] = filtered_items

    # -------------------------
    # 뉴스 출력 (카드 / expander 형태)
    # -------------------------
    total_count = sum(len(v) for v in news_data.values())
    st.write(f"총 **{total_count}건**의 뉴스가 있습니다.")

    if total_count == 0:
        st.info("현재 조건에 맞는 뉴스가 없습니다.")
        return

    for keyword, items in news_data.items():
        if not items:
            continue

        st.markdown(f"### 🔸 키워드: **{keyword}**")

        for idx, item in enumerate(items, start=1):
            with st.expander(f"{idx}. {item['title']}"):
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.write(f"**게시일**: {item['published_display']}")
                    st.write(f"**출처**: {item['source']}")
                    if item["summary"]:
                        st.write("---")
                        st.write(item["summary"], unsafe_allow_html=True)

                with col2:
                    st.link_button(
                        "원문 보기",
                        item["link"],
                        use_container_width=True,
                    )

        st.markdown("---")


if __name__ == "__main__":
    main()