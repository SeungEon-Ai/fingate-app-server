"""
금융 뉴스 우선순위 정렬.

RSS는 여러 언론사에서 가져오기 때문에 사회/문화/국제 일반 뉴스가 섞인다.
앱 목적이 금융 뉴스이므로, 금융/증시/기업 관련 뉴스를 먼저 노출한다.
"""
from typing import Any, List


HIGH_PRIORITY_KEYWORDS = {
    "코스피": 100,
    "코스닥": 95,
    "반도체": 90,
    "나스닥": 90,
    "뉴욕증시" : 90,
    "S&P500": 90,
    "다우" : 90,
    "AI": 80,
    "인공지능": 80,
    "엔비디아": 80,
    "삼성전자": 80,
    "하이닉스": 75,
    "증시": 75,
    "주가": 70,
    "시가총액": 70,
    "시총": 70,
    "상승": 35,
    "하락": 35,
    "급등": 45,
    "급락": 45,
    "환율": 75,
    "원달러": 75,
    "달러": 60,
    "금리": 75,
    "국채": 60,
    "연준": 65,
    "FOMC": 65,
    "물가": 55,
    "수출": 55,
    "실적": 60,
    "영업이익": 60,
    "매출": 50,
    "금융위": 55,
    "기재부": 50,
    "부동산": 45,
    "분양": 35,
    "은행": 50,
    "보험": 45,
    "증권": 55,
    "투자": 55,
    "채권": 50,
    "원전": 45,
    "방산": 45,
    "에어로스페이스": 50,
}


LOW_PRIORITY_KEYWORDS = {
    "드라마": -80,
    "방송": -70,
    "연예": -90,
    "가수": -90,
    "배우": -90,
    "예능": -90,
    "영화": -70,
    "문화": -60,
    "맛집": -70,
    "음식": -60,
    "사고": -20,
    "사망": -25,
    "부상": -25,
    "검찰": -40,
    "재판": -40,
    "경찰": -40,
    "시신": -80,
}


SOURCE_SCORE = {
    "hankyung_economy": 30,
    "hankyung_finance": 35,
    "hankyung_it": 20,
    "mk_stock": 35,
    "mk_economy": 30,
    "mk_business": 25,
    "mk_realestate": 20,
    "einfomax_stock": 35,
    "einfomax_company": 30,
    "einfomax_issue": 25,
    "fnnews_stock": 30,
    "fnnews_finance": 30,
    "fnnews_economy": 25,
    "yonhapnewstv_economy": 25,
    "yonhapnewstv_stock": 30,
    "korea_fsc": 20,
    "korea_moef": 20,
}


def _get_text(item: Any) -> str:
    title = getattr(item, "title", "") or ""
    summary = getattr(item, "raw_summary", "") or ""
    source = getattr(item, "source", "") or ""

    if isinstance(item, dict):
        title = item.get("title", "") or ""
        summary = item.get("summary", "") or item.get("raw_summary", "") or ""
        source = item.get("source", "") or ""

    return f"{source} {title} {summary}"


def _get_source(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("source") or "")
    return str(getattr(item, "source", "") or "")


def financial_score(item: Any) -> int:
    text = _get_text(item)
    source = _get_source(item)

    score = SOURCE_SCORE.get(source, 0)

    for keyword, value in HIGH_PRIORITY_KEYWORDS.items():
        if keyword.lower() in text.lower():
            score += value

    for keyword, value in LOW_PRIORITY_KEYWORDS.items():
        if keyword.lower() in text.lower():
            score += value

    return score


def rank_news_items(items: List[Any]) -> List[Any]:
    """금융 관련성이 높은 뉴스가 먼저 오도록 정렬."""
    return sorted(
        items,
        key=lambda item: financial_score(item),
        reverse=True,
    )