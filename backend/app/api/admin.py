"""
관리자 엔드포인트 (cron / 트리거).

POST /admin/fetch
- RSS 수집
- DB 저장
- Gemini 배치 요약

보안:
Authorization: Bearer <ADMIN_TOKEN> 헤더 필요.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.exceptions import LLMError
from app.core.logger import get_logger
from app.database import get_db
from app.schemas.news import FetchResponse
from app.services import news_collector, news_repository
from app.services.llm_processor import process_news_batch

logger = get_logger(__name__)
router = APIRouter()


# Gemini 무료 할당량을 고려한 기본값
# 10개씩 묶으면 뉴스 50개를 Gemini 5번 호출로 처리 가능
BATCH_SIZE = 10
AI_PROCESS_LIMIT = 10


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
def trigger_fetch(db: Session = Depends(get_db)):
    """RSS 수집 → DB 저장 → LLM 배치 처리.

    매일 아침 6시 자동 실행을 기준으로 사용.
    """
    logger.info("=== Fetch job started ===")

    # 1단계: RSS 수집
    collected = news_collector.fetch_all()

    inserted = 0
    skipped = 0

    for item in collected:
        if news_repository.url_exists(db, item.url):
            skipped += 1
            continue

        if news_repository.insert_raw(db, item):
            inserted += 1
        else:
            skipped += 1

    logger.info("RSS phase: inserted=%d, skipped=%d", inserted, skipped)

    # 2단계: LLM 배치 처리
    # 최신 미처리 뉴스 중 최대 AI_PROCESS_LIMIT개만 처리
    unprocessed = news_repository.find_unprocessed(db, limit=AI_PROCESS_LIMIT)

    processed = 0
    errors = 0

    logger.info(
        "LLM batch phase: targets=%d, batch_size=%d",
        len(unprocessed),
        BATCH_SIZE,
    )

    for batch in _chunk_list(unprocessed, BATCH_SIZE):
        batch_ids = [news.id for news in batch]

        try:
            results = process_news_batch(batch)

            batch_processed = 0
            for news in batch:
                result = results.get(news.id)

                if result is None:
                    logger.warning(
                        "LLM batch missing result for news id=%d",
                        news.id,
                    )
                    errors += 1
                    continue

                news_repository.apply_processing(db, news.id, result)
                processed += 1
                batch_processed += 1

            logger.info(
                "LLM batch done: ids=%s processed=%d",
                batch_ids,
                batch_processed,
            )

        except LLMError as e:
            logger.warning(
                "LLM batch failed for news ids=%s: %s",
                batch_ids,
                e,
            )
            errors += len(batch)

            # 할당량 초과나 API 오류가 나면 뒤 배치도 연쇄 실패 가능성이 높으므로 중단
            break

    logger.info("LLM phase: processed=%d, errors=%d", processed, errors)
    logger.info("=== Fetch job done ===")

    return FetchResponse(
        collected=inserted,
        processed=processed,
        skipped=skipped,
        errors=errors,
    )