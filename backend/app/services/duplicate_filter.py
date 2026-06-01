"""
뉴스 중복 제거 유틸.

URL이 달라도 같은 이슈인 뉴스가 여러 언론사/RSS에서 반복 수집된다.
예:
- 한화에어로스페이스 사고로 2명 사망
- 한화에어로스페이스 대전공장 폭발사고
- 한화에어로스페이스 사고, 부상자 발생

따라서 URL뿐 아니라 제목의 핵심 엔티티와 이벤트 유형을 기준으로 중복 제거한다.
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
    "발표",
    "확인",
    "기자",
}


EVENT_GROUPS = {
    "accident": {
        "사고",
        "폭발",
        "화재",
        "사망",
        "부상",
        "매몰",
        "붕괴",
        "인명피해",
        "대피",
        "구조",
        "현장",
        "공장",
    },
    "stock_rise": {
        "상승",
        "급등",
        "강세",
        "신고가",
        "돌파",
        "시가총액",
        "시총",
        "랠리",
    },
    "stock_fall": {
        "하락",
        "급락",
        "약세",
        "하한가",
        "부진",
    },
    "earnings": {
        "실적",
        "영업이익",
        "매출",
        "순이익",
        "흑자",
        "적자",
        "어닝",
    },
    "rate_fx": {
        "금리",
        "환율",
        "달러",
        "원화",
        "국채",
        "연준",
        "fomc",
    },
    "policy": {
        "정부",
        "정책",
        "규제",
        "지원",
        "대책",
        "금융위",
        "기재부",
    },
}


KNOWN_ENTITIES = [
    "한화에어로스페이스",
    "삼성전자",
    "SK하이닉스",
    "현대차",
    "기아",
    "LG에너지솔루션",
    "네이버",
    "카카오",
    "셀트리온",
    "두산에너빌리티",
    "포스코",
    "POSCO",
    "코스피",
    "코스닥",
    "나스닥",
    "S&P500",
    "엔비디아",
    "테슬라",
    "애플",
    "마이크로소프트",
]


def _get_title(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("title") or "")
    return str(getattr(item, "title", "") or "")


def _normalize_title(title: str) -> str:
    text = title.lower()

    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)

    text = text.replace("2천조", "2000조")
    text = text.replace("2천 조", "2000조")
    text = text.replace("시총", "시가총액")
    text = re.sub(r"시가\s*총액", "시가총액", text)

    text = re.sub(r"(\d),(\d)", r"\1\2", text)

    text = re.sub(r"[\"'‘’“”·ㆍ….,!?;:~\-_/|↑↓]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _tokens(title: str) -> set[str]:
    normalized = _normalize_title(title)
    raw_tokens = re.findall(r"[가-힣a-zA-Z0-9]+", normalized)

    tokens = set()

    for token in raw_tokens:
        token = token.strip()

        if len(token) < 2:
            continue

        if token in STOPWORDS:
            continue

        token = token.replace("2000조원", "2000조")
        tokens.add(token)

    if "한화에어로스페이스" in normalized:
        tokens.add("한화에어로스페이스")

    if "삼성전자" in normalized:
        tokens.add("삼성전자")

    if "시가총액" in normalized:
        tokens.add("시가총액")

    if "2000조" in normalized:
        tokens.add("2000조")

    return tokens


def _extract_entities(title: str) -> set[str]:
    normalized = _normalize_title(title)
    entities = set()

    for entity in KNOWN_ENTITIES:
        if entity.lower() in normalized:
            entities.add(entity.lower())

    if "한화에어로스페이스" in normalized:
        entities.add("한화에어로스페이스")

    return entities


def _event_groups(title: str) -> set[str]:
    normalized = _normalize_title(title)
    groups = set()

    for group_name, keywords in EVENT_GROUPS.items():
        for keyword in keywords:
            if keyword.lower() in normalized:
                groups.add(group_name)
                break

    return groups


def _char_ngrams(text: str, n: int = 2) -> set[str]:
    text = re.sub(r"\s+", "", _normalize_title(text))

    if len(text) < n:
        return {text} if text else set()

    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0

    return len(a & b) / len(a | b)


def is_duplicate_news(a: Any, b: Any) -> bool:
    title_a = _get_title(a)
    title_b = _get_title(b)

    if not title_a or not title_b:
        return False

    norm_a = _normalize_title(title_a)
    norm_b = _normalize_title(title_b)

    if not norm_a or not norm_b:
        return False

    if norm_a == norm_b:
        return True

    tokens_a = _tokens(title_a)
    tokens_b = _tokens(title_b)

    entities_a = _extract_entities(title_a)
    entities_b = _extract_entities(title_b)

    events_a = _event_groups(title_a)
    events_b = _event_groups(title_b)

    # 1. 사고/폭발/사망 같은 동일 사건만 강하게 묶는다.
    # 주가 상승/하락 뉴스는 같은 기업이라도 서로 다른 이슈일 수 있으므로
    # 여기서 무조건 중복 처리하지 않는다.
    if (
        entities_a
        and entities_b
        and (entities_a & entities_b)
        and "accident" in events_a
        and "accident" in events_b
    ):
        return True

    # 2. 강한 이벤트 조합 직접 처리
    # 삼성전자 시총 2000조 같은 경우
    strong_combos = [
        {"삼성전자", "시가총액", "2000조"},
        {"한화에어로스페이스", "사고"},
        {"한화에어로스페이스", "사망"},
        {"한화에어로스페이스", "폭발"},
    ]

    for combo in strong_combos:
        if combo.issubset(tokens_a) and combo.issubset(tokens_b):
            return True

    # 3. 제목 문장 유사도
    ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
    if ratio >= 0.66:
        return True

    # 4. 토큰 유사도
    token_jaccard = _jaccard(tokens_a, tokens_b)
    if len(tokens_a & tokens_b) >= 3 and token_jaccard >= 0.34:
        return True

    # 5. 글자 2-gram 유사도
    ngram_jaccard = _jaccard(_char_ngrams(title_a), _char_ngrams(title_b))
    if ngram_jaccard >= 0.48:
        return True

    return False


def dedupe_collected_news(items: List[Any]) -> List[Any]:
    result: List[Any] = []

    for item in items:
        if any(is_duplicate_news(item, existing) for existing in result):
            continue

        result.append(item)

    return result


def dedupe_news_dicts(items: List[dict]) -> List[dict]:
    result: List[dict] = []

    for item in items:
        if any(is_duplicate_news(item, existing) for existing in result):
            continue

        result.append(item)

    return result