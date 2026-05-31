"""
DB 연결 단일 관리 지점.

- engine: SQLAlchemy 엔진 (앱당 1개)
- SessionLocal: 세션 팩토리
- Base: 모델 베이스 클래스 (모델은 app/models/에서 상속)
- get_db: FastAPI 의존성 (라우터에서 Depends(get_db))
- init_db: 앱 시작 시 테이블 생성
"""
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# SQLite는 같은 연결 객체를 여러 스레드에서 쓰려면 check_same_thread=False 필요
_connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """모든 SQLAlchemy 모델은 이 클래스를 상속."""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI 라우터용 DB 세션 의존성."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """앱 시작 시 호출. 테이블이 없으면 생성한다.

    모델 모듈을 import해야 Base.metadata에 등록됨.
    """
    # 모든 모델 import (등록을 위해)
    from app.models import news  # noqa: F401

    Base.metadata.create_all(bind=engine)
