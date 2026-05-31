"""
RSS 뉴스 수집.

책임:
- RSS URL 목록에서 뉴스 수집
- 너무 오래된 뉴스는 제외
- 소스별 수집 개수 제한
- 전체 수집 개수 제한
- DB·LLM 처리는 하지 않음

운영 방식:
- 매일 아침 6시에 실행될 것을 기준으로 최근 36시간 이내 뉴스만 수집
- 여러 RSS 소스에서 조금씩 가져와 뉴스 다양성을 확보
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from calendar import timegm
from typing import List
import html
import re

import feedparser
import httpx

from app.core.exceptions import CollectorError
from app.core.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# RSS 소스 목록
# ============================================================
# 여러 언론사/섹션에서 조금씩 가져오는 구조
SOURCES: List[tuple[str, str]] = [
    # 한국경제
    ("hankyung_economy", "https://www.hankyung.com/feed/economy"),
    ("hankyung_finance", "https://www.hankyung.com/feed/finance"),
    ("hankyung_international", "https://www.hankyung.com/feed/international"),
    ("hankyung_it", "https://www.hankyung.com/feed/it"),

    # 매일경제
    ("mk_headline", "https://www.mk.co.kr/rss/30000001/"),
    ("mk_economy", "https://www.mk.co.kr/rss/30100041/"),
    ("mk_international", "https://www.mk.co.kr/rss/30300018/"),
    ("mk_stock", "https://www.mk.co.kr/rss/50200011/"),
    ("mk_realestate", "https://www.mk.co.kr/rss/50300009/"),

    # 조선일보
    ("chosun_economy", "https://www.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml"),
    ("chosun_international", "https://www.chosun.com/arc/outboundfeeds/rss/category/international/?outputType=xml"),

    # 연합뉴스TV
    ("yonhapnewstv_latest", "http://www.yonhapnewstv.co.kr/browse/feed/"),
    ("yonhapnewstv_economy", "http://www.yonhapnewstv.co.kr/category/news/economy/feed/"),
    ("yonhapnewstv_stock", "http://www.yonhapnewstv.co.kr/category/news/stock/feed/"),
    ("yonhapnewstv_international", "http://www.yonhapnewstv.co.kr/category/news/international/feed/"),

    # 연합뉴스경제TV
    ("yonhap_economytv_all", "https://www.yonhapnewseconomytv.com/rss/allArticle.xml"),
    ("yonhap_economytv_top", "https://www.yonhapnewseconomytv.com/rss/clickTop.xml"),

    # 연합인포맥스
    ("einfomax_all", "https://news.einfomax.co.kr/rss/allArticle.xml"),
    ("einfomax_stock", "https://news.einfomax.co.kr/rss/S1N2.xml"),
    ("einfomax_company", "https://news.einfomax.co.kr/rss/S1N7.xml"),
    ("einfomax_issue", "https://news.einfomax.co.kr/rss/S1N9.xml"),

    # 파이낸셜뉴스
    ("fnnews_economy", "http://www.fnnews.com/rss/r20/fn_realnews_economy.xml"),
    ("fnnews_stock", "http://www.fnnews.com/rss/r20/fn_realnews_stock.xml"),
    ("fnnews_finance", "http://www.fnnews.com/rss/r20/fn_realnews_finance.xml"),
    ("fnnews_international", "http://www.fnnews.com/rss/r20/fn_realnews_international.xml"),
    ("fnnews_realestate", "http://www.fnnews.com/rss/r20/fn_realnews_realestate.xml"),

    # 매일경제TV
    ("mk_tv_stock", "https://mbnmoney.mbn.co.kr/rss/news/stock"),
    ("mk_tv_estate", "https://mbnmoney.mbn.co.kr/rss/news/estate"),
    ("mk_tv_finance", "https://mbnmoney.mbn.co.kr/rss/news/finance"),

    # 정책/공공 보조 소스
    # 언론사는 아니지만 금융/경제 정책 뉴스 보조용으로 사용
    ("korea_policy", "https://www.korea.kr/rss/policy.xml"),
    ("korea_moef", "https://www.korea.kr/rss/dept_moef.xml"),
    ("korea_fsc", "https://www.korea.kr/rss/dept_fsc.xml"),
]



# ============================================================
# 수집 제한 설정
# ============================================================

# 최근 36시간 이내 뉴스만 수집
MAX_NEWS_AGE_HOURS = 36

# RSS 소스 하나당 최대 몇 개 가져올지
# 예: 13개 소스 × 6개 = 이론상 78개
MAX_ITEMS_PER_SOURCE = 2

# 전체 수집 최대 개수
# 앱 초기 버전에서는 하루 50개 정도면 충분
MAX_TOTAL_ITEMS = 50


@dataclass
class CollectedNews:
    """RSS에서 막 수집한 뉴스 1건 (LLM 처리 전)."""
    source: str
    title: str
    url: str
    raw_summary: str | None
    published_at: datetime | None


def _clean_xml_entities(text: str) -> str:
    """RSS XML 안의 HTML 엔티티 문제를 완화한다."""
    xml_builtin = {"amp", "lt", "gt", "quot", "apos"}

    def replace_named_entity(match: re.Match) -> str:
        name = match.group(1)

        if name in xml_builtin:
            return match.group(0)

        decoded = html.unescape(match.group(0))
        if decoded != match.group(0):
            return decoded

        return ""

    text = re.sub(r"&([A-Za-z][A-Za-z0-9]+);", replace_named_entity, text)

    text = re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)",
        "&amp;",
        text,
    )
    return text


def _download_rss(url: str) -> str:
    """RSS URL을 직접 다운로드한다."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    response = httpx.get(
        url,
        headers=headers,
        timeout=15.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _parse_published(entry) -> datetime | None:
    """feedparser entry → UTC 기준 naive datetime.

    DB가 datetime.utcnow() 기반 naive datetime을 쓰고 있으므로
    published_at도 UTC naive datetime으로 맞춘다.
    """
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime.fromtimestamp(timegm(t), tz=timezone.utc).replace(tzinfo=None)
            except (ValueError, OSError):
                continue
    return None


def _is_recent_news(published_at: datetime | None) -> bool:
    """최근 뉴스인지 판단."""
    if published_at is None:
        return False

    now_utc = datetime.utcnow()
    cutoff = now_utc - timedelta(hours=MAX_NEWS_AGE_HOURS)

    # RSS 시간대가 약간 미래로 들어오는 경우를 방어
    future_limit = now_utc + timedelta(hours=3)

    return cutoff <= published_at <= future_limit


def fetch_from_source(source_name: str, url: str) -> List[CollectedNews]:
    """RSS 1개에서 뉴스 수집."""
    logger.info("Fetching RSS: %s (%s)", source_name, url)

    try:
        rss_text = _download_rss(url)
        rss_text = _clean_xml_entities(rss_text)
        feed = feedparser.parse(rss_text)
    except Exception as e:
        logger.warning("RSS download/parse failed: %s err=%s", source_name, e)
        raise CollectorError(f"RSS parse failed: {source_name}") from e

    if feed.bozo:
        logger.warning("RSS bozo: %s err=%s", source_name, feed.bozo_exception)

    if not feed.entries:
        logger.warning("RSS empty: %s", source_name)
        return []

    items: List[CollectedNews] = []
    old_or_invalid = 0
    missing_required = 0

    for entry in feed.entries:
        # 소스당 최대 개수 제한
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break

        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()

        if not title or not link:
            missing_required += 1
            continue

        published_at = _parse_published(entry)

        # 오래된 뉴스 또는 발행일 없는 뉴스 제외
        if not _is_recent_news(published_at):
            old_or_invalid += 1
            continue

        summary = (
            entry.get("summary")
            or entry.get("description")
            or entry.get("subtitle")
            or ""
        )

        items.append(
            CollectedNews(
                source=source_name,
                title=title[:500],
                url=link[:1000],
                raw_summary=summary.strip() or None,
                published_at=published_at,
            )
        )

    logger.info(
        "Fetched %d recent items from %s "
        "(filtered_old_or_invalid=%d, missing_required=%d)",
        len(items),
        source_name,
        old_or_invalid,
        missing_required,
    )

    return items


def fetch_all() -> List[CollectedNews]:
    """모든 소스에서 수집. 일부 소스가 실패해도 나머지는 계속."""
    all_items: List[CollectedNews] = []

    for name, url in SOURCES:
        if len(all_items) >= MAX_TOTAL_ITEMS:
            break

        try:
            items = fetch_from_source(name, url)
        except CollectorError as e:
            logger.error("Source failed: %s err=%s", name, e)
            continue

        remaining = MAX_TOTAL_ITEMS - len(all_items)
        all_items.extend(items[:remaining])

    logger.info("Total collected: %d", len(all_items))
    return all_items