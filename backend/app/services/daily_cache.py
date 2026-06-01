"""
매일 갱신되는 뉴스 캐시 파일 관리.

DB 대신 daily_news.json 파일에 오늘의 AI 요약 뉴스를 저장하고,
앱은 /news/today API를 통해 이 파일을 읽는다.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List


CACHE_FILE = Path("daily_news.json")


def save_daily_news(items: List[dict[str, Any]]) -> None:
    """오늘의 뉴스 목록을 JSON 파일로 저장."""
    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "items": items,
    }

    CACHE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_daily_news(limit: int = 30, hours: int = 36) -> List[dict[str, Any]]:
    """JSON 파일에서 최근 뉴스 목록을 읽는다."""
    if not CACHE_FILE.exists():
        return []

    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    items = payload.get("items", [])
    if not isinstance(items, list):
        return []

    since = datetime.utcnow() - timedelta(hours=hours)

    filtered: List[dict[str, Any]] = []

    for item in items:
        published_raw = item.get("published_at")

        try:
            published_at = datetime.fromisoformat(published_raw)
        except Exception:
            published_at = None

        if published_at is not None and published_at < since:
            continue

        filtered.append(item)

    filtered.sort(
        key=lambda x: (
            int(x.get("importance") or 0),
            x.get("published_at") or "",
        ),
        reverse=True,
    )

    return filtered[:limit]