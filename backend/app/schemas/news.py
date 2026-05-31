"""
API 입출력 스키마 (Pydantic).

DB 모델(app/models/news.py)과 분리한 이유:
- DB 컬럼이 그대로 API로 새어나가는 걸 막기 위함
- API 응답 포맷을 DB 변경 없이 바꿀 수 있게 하기 위함
"""
from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class NewsItem(BaseModel):
    """앱에 노출되는 뉴스 1건 형식."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    title: str
    url: str
    summary: str | None = None
    context: str | None = None
    importance: int | None = Field(None, ge=1, le=5)
    tags: List[str] = Field(default_factory=list)
    published_at: datetime | None = None

    @classmethod
    def from_orm_news(cls, news) -> "NewsItem":
        """SQLAlchemy News → Pydantic 변환. tags 콤마 문자열을 리스트로."""
        tags = (
            [t.strip() for t in news.tags.split(",") if t.strip()]
            if news.tags
            else []
        )
        return cls(
            id=news.id,
            source=news.source,
            title=news.title,
            url=news.url,
            summary=news.summary,
            context=news.context,
            importance=news.importance,
            tags=tags,
            published_at=news.published_at,
        )


class NewsListResponse(BaseModel):
    """GET /news/today 응답."""

    date: str  # YYYY-MM-DD (KST 기준)
    count: int
    items: List[NewsItem]


class FetchResponse(BaseModel):
    """POST /admin/fetch 응답."""

    collected: int  # RSS에서 새로 가져온 개수
    processed: int  # Gemini로 요약한 개수
    skipped: int    # 이미 있어서 스킵
    errors: int     # 처리 실패
