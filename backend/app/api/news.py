"""
공개 뉴스 엔드포인트.

GET /news/today  - 오늘의 큐레이션 뉴스
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.news import NewsItem, NewsListResponse
from app.services import news_repository

router = APIRouter()

KST = ZoneInfo("Asia/Seoul")


@router.get("/today", response_model=NewsListResponse)
def get_today_news(
    limit: int = Query(7, ge=1, le=30),
    hours: int = Query(24, ge=1, le=72),
    db: Session = Depends(get_db),
):
    """최근 N시간 안의 큐레이션 뉴스 상위 limit개."""
    rows = news_repository.get_today_top(db, limit=limit, hours=hours)
    items = [NewsItem.from_orm_news(r) for r in rows]
    return NewsListResponse(
        date=datetime.now(KST).strftime("%Y-%m-%d"),
        count=len(items),
        items=items,
    )
