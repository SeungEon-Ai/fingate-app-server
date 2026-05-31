"""
로깅 설정.

다른 모듈에서:
    from app.core.logger import get_logger
    logger = get_logger(__name__)
"""
import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """앱 시작 시 1회 호출."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    # 기존 핸들러 제거 (uvicorn 등 중복 방지)
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)

    # 너무 시끄러운 라이브러리 억제
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """모듈별 로거 반환."""
    return logging.getLogger(name)
