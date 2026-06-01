"""
관리자 엔드포인트.

POST /admin/fetch
- RSS 수집
- Gemini 배치 요약
- DB 저장 대신 daily_news.json 파일 갱신

보안:
Authorization: Bearer <ADMIN_TOKEN> 헤더 필요.
"""
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.config import settings
from app.core.exceptions import LLMError
from app.core.logger import get_logger
from app.schemas.news import FetchResponse
from app.services import news_collector
from app.services.daily_cache import save_daily_news
from app.services.llm_processor import process_news_batch
from app.services.duplicate_filter import dedupe_collected_news

logger = get_logger(__name__)
router = APIRouter()


BATCH_SIZE = 10
AI_PROCESS_LIMIT = 30


def verify_admin(authorization: str | None = Header(None)) -> None:
    """Bearer 토큰 검증."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
        )

    token = authorization.removeprefix("Bearer ").strip()

    if token != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


def _chunk_list(items: list, size: int):
    """리스트를 size 단위로 자르기."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


@router.post(
    "/fetch",
    response_model=FetchResponse,
    dependencies=[Depends(verify_admin)],
)
def trigger_fetch():
    """RSS 수집 → Gemini 배치 요약 → daily_news.json 갱신."""
    logger.info("=== Daily fetch job started ===")

    collected = news_collector.fetch_all()

# 1차: URL 기준 중복 제거
url_unique_items = []
seen_urls = set()

for item in collected:
    if item.url in seen_urls:
        continue
    seen_urls.add(item.url)
    url_unique_items.append(item)

# 2차: 제목 유사도 기준 중복 제거
unique_items = dedupe_collected_news(url_unique_items)

logger.info(
    "Dedup phase: collected=%d url_unique=%d title_unique=%d removed=%d",
    len(collected),
    len(url_unique_items),
    len(unique_items),
    len(collected) - len(unique_items),
)
    # Gemini 요약 대상 제한
    targets = unique_items[:AI_PROCESS_LIMIT]

    # process_news_batch가 id/title/source/raw_summary를 가진 객체를 기대하므로
    # SimpleNamespace로 임시 입력 객체를 만든다.
    batch_inputs = []
    id_to_raw = {}

    for idx, item in enumerate(targets, start=1):
        obj = SimpleNamespace(
            id=idx,
            source=item.source,
            title=item.title,
            url=item.url,
            raw_summary=item.raw_summary,
            published_at=item.published_at,
        )
        batch_inputs.append(obj)
        id_to_raw[idx] = item

    processed_results = {}
    processed = 0
    errors = 0

    logger.info(
        "LLM batch phase: targets=%d, batch_size=%d",
        len(batch_inputs),
        BATCH_SIZE,
    )

    for batch in _chunk_list(batch_inputs, BATCH_SIZE):
        batch_ids = [news.id for news in batch]

        try:
            results = process_news_batch(batch)
            processed_results.update(results)
            processed += len(results)

            logger.info(
                "LLM batch done: ids=%s processed=%d",
                batch_ids,
                len(results),
            )

        except LLMError as e:
            logger.warning(
                "LLM batch failed for news ids=%s: %s",
                batch_ids,
                e,
            )
            errors += len(batch)
            break

    # 앱에 내려줄 오늘 뉴스 JSON 만들기
    daily_news = []

    for obj in batch_inputs:
        raw_item = id_to_raw[obj.id]
        result = processed_results.get(obj.id)

        # Gemini 실패 시에도 제목/출처/원문 링크는 보여줄 수 있게 저장
        daily_news.append(
            {
                "id": obj.id,
                "source": raw_item.source,
                "title": raw_item.title,
                "url": raw_item.url,
                "summary": result.summary if result else "",
                "context": result.context if result else "",
                "importance": result.importance if result else 1,
                "tags": result.tags if result else [],
                "published_at": (
                    raw_item.published_at.isoformat()
                    if raw_item.published_at
                    else None
                ),
            }
        )

    save_daily_news(daily_news)

    logger.info(
        "Daily cache saved: collected=%d unique=%d processed=%d errors=%d",
        len(collected),
        len(unique_items),
        processed,
        errors,
    )
    logger.info("=== Daily fetch job done ===")

    return FetchResponse(
        collected=len(unique_items),
        processed=processed,
        skipped=max(0, len(unique_items) - len(targets)),
        errors=errors,
    )