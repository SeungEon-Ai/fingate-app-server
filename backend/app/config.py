"""
환경변수 단일 관리 지점.

원칙: 코드 어디에서도 os.environ을 직접 읽지 않는다.
모두 `from app.config import settings`로 가져온다.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """앱 전역 설정. .env 파일과 환경변수에서 자동 로드."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"

    # 관리자 (cron 엔드포인트 보호)
    admin_token: str = "dev-only-change-me"

    # DB
    database_url: str = "sqlite:///./fingate.db"

    # CORS — 콤마 구분 문자열
    cors_origins: str = "*"

    # 환경
    env: str = "development"
    log_level: str = "INFO"

    @property
    def cors_origins_list(self) -> List[str]:
        """콤마 구분 문자열 → 리스트."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """캐시된 settings 인스턴스. 테스트 시 override 가능."""
    return Settings()


# 편의용 전역 — 일반 코드는 이걸 그냥 import해서 쓰면 됨
settings = get_settings()
