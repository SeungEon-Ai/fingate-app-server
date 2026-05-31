"""
FastAPI 진입점.
이 파일은 얇게 유지한다. 비즈니스 로직은 app/services/, 엔드포인트는 app/api/.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, news
from app.config import settings
from app.core.logger import setup_logging, get_logger
from app.database import init_db

setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작 시 DB 초기화, 종료 시 정리."""
    logger.info("Starting fingate backend (env=%s)", settings.env)
    init_db()
    logger.info("DB initialized at %s", settings.database_url)
    yield
    logger.info("Shutting down fingate backend")


app = FastAPI(
    title="Fingate API",
    description="금융 뉴스 큐레이션 백엔드",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — v0.1은 모두 허용, 배포 후 앱 도메인만 허용으로 좁힐 것
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(news.router, prefix="/news", tags=["news"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])


@app.get("/")
def root():
    """루트 - 살아있는지 확인용."""
    return {"service": "fingate", "version": "0.1.0", "status": "ok"}


@app.get("/health")
def health():
    """Render healthCheckPath용."""
    return {"status": "healthy"}
