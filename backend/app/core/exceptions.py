"""
커스텀 예외.

원칙:
- 서비스/리포지토리는 도메인 예외만 raise (HTTP 모름)
- API 계층에서 HTTPException으로 변환
"""


class FingateError(Exception):
    """모든 앱 예외의 부모."""
    pass


class LLMError(FingateError):
    """Gemini 호출 실패. 일시적 오류일 수 있음 (재시도 가능)."""
    pass


class CollectorError(FingateError):
    """RSS/크롤링 실패."""
    pass


class NotFoundError(FingateError):
    """리소스 없음. API 계층에서 404로 변환."""
    pass


class UnauthorizedError(FingateError):
    """인증 실패. API 계층에서 401로 변환."""
    pass
