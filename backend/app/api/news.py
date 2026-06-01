"""
뉴스 조회 API.

DB 대신 daily_news.json 파일에서 오늘의 뉴스 목록을 읽는다.
조회 시점에도 제목 유사도 기준 중복 제거를 한 번 더 수행한다.
"""
from fastapi import APIRouter, Query

from app.services.daily_cache import load_daily_news
from app.services.duplicate_filter import dedupe_news_dicts

router = APIRouter()


@router.get("/today")
def get_today_news(
    limit: int = Query(30, ge=1, le=100),
    hours: int = Query(36, ge=1, le=168),
):
    """최근 N시간 이내의 오늘 뉴스 목록."""
    # 중복 제거 후 limit을 적용하기 위해 넉넉하게 읽는다.
    items = load_daily_news(limit=100, hours=hours)
    items = dedupe_news_dicts(items)

    return items[:limit]