"""
뉴스 DB 모델.

이 파일은 DB 스키마만 정의한다. 비즈니스 로직은 services/news_repository.py.
"""
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class News(Base):
    """수집·요약된 뉴스 1건."""

    __tablename__ = "news"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 원본
    source: Mapped[str] = mapped_column(String(64), index=True)  # "naver", "wsj" 등
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(1024))
    raw_summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # RSS가 준 요약
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    # LLM 처리 결과
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)         # 3줄 TL;DR
    context: Mapped[str | None] = mapped_column(Text, nullable=True)         # 왜 중요한가
    importance: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # 1~5
    tags: Mapped[str | None] = mapped_column(String(256), nullable=True)     # "코스피,금리" 콤마 구분

    # 메타
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 같은 URL 중복 수집 방지
    __table_args__ = (
        UniqueConstraint("url", name="uq_news_url"),
    )

    def __repr__(self) -> str:
        return f"<News id={self.id} src={self.source} title={self.title[:30]!r}>"
