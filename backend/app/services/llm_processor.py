"""
Gemini를 사용해 뉴스를 요약·평가한다.

기존 방식:
- 뉴스 1개당 Gemini 요청 1회

현재 방식:
- 뉴스 여러 개를 묶어서 Gemini 요청 1회로 처리
- 무료 할당량/비용 절감을 위해 배치 요약 구조 사용
"""
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from google import genai
from google.genai import types

from app.config import settings
from app.core.exceptions import LLMError
from app.core.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 프롬프트
# ============================================================
SYSTEM_INSTRUCTION = """\
당신은 한국 금융시장 뉴스 큐레이션 앱의 AI 분석 어시스턴트입니다.
사용자는 주식·경제 뉴스를 빠르게 이해하고 싶은 일반 투자자입니다.

여러 개의 뉴스가 주어지면, 각 뉴스별로 아래 정보를 JSON으로 반환하세요.

각 뉴스별 출력 항목:
- news_id:
  입력으로 받은 뉴스 ID를 그대로 반환하세요.

- summary:
  한국어 2~3문장 요약.
  기사 내용을 그대로 베끼지 말고 핵심 사실을 재구성해서 설명하세요.
  원문 기사를 대체할 정도로 길게 쓰지 마세요.

- context:
  이 뉴스가 왜 중요한지 2~3문장으로 설명하세요.
  가능한 경우 시장 전체, 관련 산업, 금리, 환율, 정책, 기업 실적, 투자심리에 미칠 수 있는 영향을 설명하세요.
  특정 종목의 매수·매도 판단이 아니라 뉴스의 의미와 배경을 설명하는 데 집중하세요.

- importance:
  1~5 사이의 정수로 평가하세요.
  5 = 시장 전체에 큰 영향 가능성
  4 = 특정 산업이나 섹터에 큰 영향 가능성
  3 = 관련 기업이나 업종에 의미 있는 뉴스
  2 = 참고할 만한 일반 경제 뉴스
  1 = 영향이 제한적인 뉴스

- tags:
  관련 키워드 3~5개.
  종목명, 섹터명, 경제지표, 정책 이슈, 시장 키워드 중심으로 작성하세요.

작성 규칙:
- 반드시 JSON만 출력하세요.
- 투자 권유, 매수/매도 추천, 목표가 제시를 절대 하지 마세요.
- “사야 한다”, “팔아야 한다”, “급등 확실”, “수익 보장” 같은 표현을 쓰지 마세요.
- 확실하지 않은 내용은 단정하지 말고 “가능성이 있다”, “영향을 줄 수 있다”처럼 조심스럽게 표현하세요.
- 기사 본문을 그대로 복사하지 말고, AI가 이해한 내용을 요약·해설하는 방식으로 작성하세요.
- 모든 내용은 한국어로 작성하세요.
"""


SINGLE_USER_PROMPT_TEMPLATE = """\
[뉴스 제목]
{title}

[원본 요약]
{raw_summary}

[출처]
{source}

위 뉴스를 JSON으로 분석하세요. JSON 외 다른 텍스트는 출력하지 마세요.
"""


BATCH_USER_PROMPT_TEMPLATE = """\
아래 뉴스 목록을 각각 분석하세요.

반드시 다음 JSON 형식으로만 반환하세요.

{{
  "items": [
    {{
      "news_id": 1,
      "summary": "요약",
      "context": "왜 중요한지",
      "importance": 3,
      "tags": ["키워드1", "키워드2", "키워드3"]
    }}
  ]
}}

[뉴스 목록]
{news_list}
"""


SINGLE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "context": {"type": "string"},
        "importance": {"type": "integer", "minimum": 1, "maximum": 5},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 5,
        },
    },
    "required": ["summary", "context", "importance", "tags"],
}


BATCH_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "news_id": {"type": "integer"},
                    "summary": {"type": "string"},
                    "context": {"type": "string"},
                    "importance": {"type": "integer", "minimum": 1, "maximum": 5},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 5,
                    },
                },
                "required": ["news_id", "summary", "context", "importance", "tags"],
            },
        }
    },
    "required": ["items"],
}


# ============================================================
# 결과 형식
# ============================================================
@dataclass
class ProcessedNews:
    summary: str
    context: str
    importance: int
    tags: List[str]


# ============================================================
# Gemini 클라이언트
# ============================================================
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """싱글톤 Gemini 클라이언트."""
    global _client

    if _client is None:
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY not set")

        _client = genai.Client(api_key=settings.gemini_api_key)
        logger.info("Gemini client initialized (model=%s)", settings.gemini_model)

    return _client


def _extract_json(text: str) -> dict:
    """Gemini 응답에서 JSON 추출. 마크다운 코드펜스 제거 등 방어."""
    text = text.strip()

    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"Invalid JSON from Gemini: {text[:500]!r}") from e


def _call_gemini_json(
    prompt: str,
    response_schema: dict,
    max_output_tokens: int,
) -> dict:
    """Gemini를 호출하고 JSON dict로 반환."""
    client = _get_client()

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0.2,
                max_output_tokens=max_output_tokens,
            ),
        )
    except Exception as e:
        raise LLMError(f"Gemini API call failed: {e}") from e

    if not response.text:
        raise LLMError("Empty response from Gemini")

    return _extract_json(response.text)


def _normalize_processed(data: dict) -> ProcessedNews:
    """Gemini 응답 dict → ProcessedNews."""
    importance = int(data.get("importance", 3))

    if importance < 1:
        importance = 1
    if importance > 5:
        importance = 5

    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []

    return ProcessedNews(
        summary=str(data.get("summary", "")).strip(),
        context=str(data.get("context", "")).strip(),
        importance=importance,
        tags=[str(t).strip() for t in tags if str(t).strip()][:5],
    )


def process_news(title: str, raw_summary: str | None, source: str) -> ProcessedNews:
    """뉴스 1건을 Gemini로 분석.

    테스트용/예외용으로 남겨둔다.
    실제 운영에서는 process_news_batch 사용 권장.
    """
    prompt = SINGLE_USER_PROMPT_TEMPLATE.format(
        title=title,
        raw_summary=(raw_summary or "(요약 없음)")[:1500],
        source=source,
    )

    data = _call_gemini_json(
        prompt=prompt,
        response_schema=SINGLE_RESPONSE_SCHEMA,
        max_output_tokens=1000,
    )

    return _normalize_processed(data)


def _build_batch_news_list(news_items: List[Any]) -> str:
    """배치 프롬프트에 넣을 뉴스 목록 문자열 생성."""
    lines: List[str] = []

    for idx, news in enumerate(news_items, start=1):
        raw_summary = news.raw_summary or "(요약 없음)"
        raw_summary = raw_summary[:1000]

        lines.append(
            f"""뉴스 {idx}
- news_id: {news.id}
- source: {news.source}
- title: {news.title}
- raw_summary: {raw_summary}
"""
        )

    return "\n".join(lines)


def process_news_batch(news_items: List[Any]) -> Dict[int, ProcessedNews]:
    """뉴스 여러 건을 Gemini 요청 1회로 분석.

    반환 형식:
    {
      news_id: ProcessedNews(...)
    }
    """
    if not news_items:
        return {}

    news_list_text = _build_batch_news_list(news_items)

    prompt = BATCH_USER_PROMPT_TEMPLATE.format(
        news_list=news_list_text,
    )

    data = _call_gemini_json(
        prompt=prompt,
        response_schema=BATCH_RESPONSE_SCHEMA,
        max_output_tokens=5000,
    )

    items = data.get("items", [])

    if not isinstance(items, list):
        raise LLMError("Invalid batch response: items is not a list")

    results: Dict[int, ProcessedNews] = {}

    for item in items:
        try:
            news_id = int(item["news_id"])
            results[news_id] = _normalize_processed(item)
        except Exception as e:
            logger.warning("Invalid item in batch response: %s err=%s", item, e)
            continue

    return results