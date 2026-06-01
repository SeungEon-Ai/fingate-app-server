"""
뉴스 중복 제거 유틸.

같은 이슈가 여러 언론사/RSS에서 다른 제목과 URL로 들어오는 경우가 많다.
URL만으로는 중복 제거가 부족하므로 제목 유사도와 핵심 단어 기준으로 중복을 제거한다.
"""
import re
from difflib import SequenceMatcher
from typing import Any, List


STOPWORDS = {
    "속보",
    "단독",
    "종합",
    "장중",
    "사상",
    "최초",
    "첫",
    "오늘",
    "내일",
    "뉴스",
    "관련",
    "기준",
    "올해",
    "지난",
    "이번",
    "오전",
    "오후",
    "최대",
    "최고",
    "최저",
    "급등",
    "급락",
    "상승",
    "하락",
    "돌파",
    "마감",
}


def _get_title(item: Any) -> str:
    """dict 또는 객체에서 title 추출."""
    if isinstance(item, dict):
        return str(item.get("title") or "")
    return str(getattr(item, "title", "") or "")


def _normalize_title(title: str) -> str:
    """제목 정규화."""
    text = title.lower()

    # [속보], (종합) 같은 괄호형 수식 제거
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)

    # 숫자/표현 통일
    text = text.replace("2천조", "2000조")
    text = text.replace("2천 조", "2000조")
    text = text.replace("시총", "시가총액")
    text = re.sub(r"시가\s*총액", "시가총액", text)

    # 쉼표 숫자 제거: 2,000 → 2000
    text = re.sub(r"(\d),(\d)", r"\1\2", text)

    # 특수문자 제거
    text = re.sub(r"[\"'‘’“”·ㆍ….,!?;:~\-_/|]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _tokens(title: str) -> set[str]:
    """중복 판단용 토큰 추출."""
    normalized = _normalize_title(title)
    raw_tokens = re.findall(r"[가-힣a-zA-Z0-9]+", normalized)

    tokens = set()

    for token in raw_tokens:
        token = token.strip()

        if not token:
            continue

        # 너무 짧은 단어 제거
        if len(token) < 2:
            continue

        # 불필요한 일반 단어 제거
        if token in STOPWORDS:
            continue

        # 2000조원 → 2000조
        token = token.replace("2000조원", "2000조")

        tokens.add(token)

    return tokens


def is_duplicate_news(a: Any, b: Any) -> bool:
    """두 뉴스가 같은 이슈인지 판단."""
    title_a = _get_title(a)
    title_b = _get_title(b)

    if not title_a or not title_b:
        return False

    norm_a = _normalize_title(title_a)
    norm_b = _normalize_title(title_b)

    if not norm_a or not norm_b:
        return False

    # 완전 동일
    if norm_a == norm_b:
        return True

    # 문장 유사도
    ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
    if ratio >= 0.72:
        return True

    tokens_a = _tokens(title_a)
    tokens_b = _tokens(title_b)

    if not tokens_a or not tokens_b:
        return False

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    jaccard = len(intersection) / len(union)

    # 핵심 토큰 3개 이상 겹치고, 전체 유사도도 일정 수준 이상이면 중복
    if len(intersection) >= 3 and jaccard >= 0.42:
        return True

    # 삼성전자 + 시가총액 + 2000조 같은 강한 이벤트 조합 처리
    strong_event_tokens = {"삼성전자", "시가총액", "2000조"}
    if strong_event_tokens.issubset(tokens_a) and strong_event_tokens.issubset(tokens_b):
        return True

    return False


def dedupe_collected_news(items: List[Any]) -> List[Any]:
    """수집된 뉴스 객체 리스트 중복 제거."""
    result: List[Any] = []

    for item in items:
        duplicated = any(is_duplicate_news(item, existing) for existing in result)

        if duplicated:
            continue

        result.append(item)

    return result


def dedupe_news_dicts(items: List[dict]) -> List[dict]:
    """API 응답용 dict 뉴스 리스트 중복 제거."""
    result: List[dict] = []

    for item in items:
        duplicated = any(is_duplicate_news(item, existing) for existing in result)

        if duplicated:
            continue

        result.append(item)

    return result