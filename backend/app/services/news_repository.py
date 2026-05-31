"""
뉴스 DB 입출력 (Repository 패턴).

원칙: SQLAlchemy 쿼리는 이 파일에만. API/서비스 다른 곳에서 .query() 직접 호출 X.
이렇게 하면 DB 변경 (SQLite → Postgres) 시 이 파일만 수정.
"""
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.models.news import News
from app.services.llm_processor import ProcessedNews
from app.services.news_collector import CollectedNews

logger = get_logger(__name__)


# 매일 아침 6시 수집/요약 기준
# RSS 발행 시간 지연이나 시차 문제를 고려해서 최근 36시간 이내 뉴스만 처리
RECENT_NEWS_HOURS = 36


def url_exists(db: Session, url: str) -> bool:
    """이미 같은 URL이 DB에 있는지."""
    stmt = select(News.id).where(News.url == url).limit(1)
    return db.scalar(stmt) is not None


def insert_raw(db: Session, item: CollectedNews) -> News | None:
    """수집한 뉴스 1건을 raw로 저장 (LLM 처리 전).

    중복이면 None 반환.
    """
    news = News(
        source=item.source,
        title=item.title,
        url=item.url,
        raw_summary=item.raw_summary,
        published_at=item.published_at,
        fetched_at=datetime.utcnow(),
    )

    db.add(news)

    try:
        db.commit()
        db.refresh(news)
        return news
    except IntegrityError:
        db.rollback()
        return None


def find_unprocessed(db: Session, limit: int = 50) -> List[News]:
    """LLM 처리 안 된 최근 뉴스 가져오기.

    기존 코드처럼 모든 미처리 뉴스를 가져오면,
    2022년 같은 오래된 RSS 뉴스도 계속 AI 요약 대상에 걸릴 수 있다.

    따라서 실제 기사 발행일(published_at)이 최근 36시간 이내인 뉴스만 처리한다.
    """
    since = datetime.utcnow() - timedelta(hours=RECENT_NEWS_HOURS)

    stmt = (
        select(News)
        .where(
            News.processed_at.is_(None),
            News.published_at.is_not(None),
            News.published_at >= since,
        )
        .order_by(News.published_at.desc().nullslast())
        .limit(limit)
    )

    return list(db.scalars(stmt))


def apply_processing(db: Session, news_id: int, result: ProcessedNews) -> None:
    """LLM 처리 결과를 뉴스에 반영."""
    news = db.get(News, news_id)

    if news is None:
        return

    news.summary = result.summary
    news.context = result.context
    news.importance = result.importance
    news.tags = ",".join(result.tags)
    news.processed_at = datetime.utcnow()

    db.commit()


def get_today_top(db: Session, limit: int = 7, hours: int = 24) -> List[News]:
    """최근 N시간 안에 발행된 뉴스 중 처리 완료된 것 상위 N개.

    중요:
    - 기존 코드는 fetched_at 기준이었다.
    - 그러면 2022년 뉴스라도 오늘 수집되면 오늘 뉴스처럼 노출된다.
    - 이제는 published_at 기준으로 필터링한다.
    """
    since = datetime.utcnow() - timedelta(hours=hours)

    stmt = (
        select(News)
        .where(
            News.processed_at.is_not(None),
            News.published_at.is_not(None),
            News.published_at >= since,
        )
        .order_by(
            News.importance.desc().nullslast(),
            News.published_at.desc().nullslast(),
        )
        .limit(limit)
    )

    return list(db.scalars(stmt))


def count_total(db: Session) -> int:
    """디버그용 — 전체 뉴스 개수."""
    return db.scalar(select(func.count(News.id))) or 0