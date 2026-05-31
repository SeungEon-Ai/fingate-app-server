# Fingate 아키텍처 가이드

> **이 문서의 목적**: 코드를 수정하거나 새 기능을 추가할 때 **어디를 손대야 하는지** 한눈에 보기 위함.  
> AI 코딩 도구(Cursor, Claude, Copilot 등)에 컨텍스트로 넣으면 바이브코딩 정확도가 크게 올라간다.

## 한 줄 요약

> 금융 뉴스를 RSS로 수집 → Gemini가 요약·중요도 평가 → API로 앱에 전달.

## 전체 흐름

```
[GitHub Actions cron]
        │
        │ 매일 06:00 KST, Authorization 헤더로 호출
        ▼
[POST /admin/fetch]   ← 백엔드 (FastAPI on Render)
        │
        ├─→ news_collector  : RSS 파싱
        ├─→ news_repository : DB 저장 (중복 제외)
        ├─→ llm_processor   : Gemini 호출 (요약/평가)
        └─→ news_repository : 처리 결과 반영
                │
                ▼
        [SQLite DB]
                │
                │ GET /news/today
                ▼
        [Flutter 앱]
```

## 폴더 책임 (한 폴더 = 한 책임)

| 폴더/파일 | 책임 | 손대지 말아야 할 것 |
|----------|------|--------------------|
| `main.py` | FastAPI 앱 생성, 라우터 등록 | 비즈니스 로직 X |
| `app/config.py` | 모든 환경변수 단일 관리 | 다른 파일에서 `os.environ` 직접 읽기 X |
| `app/database.py` | DB 연결, 세션 의존성 | 쿼리·모델 정의 X |
| `app/models/` | SQLAlchemy 모델 (DB 테이블) | API 입출력 형식 X (그건 schemas) |
| `app/schemas/` | Pydantic 모델 (API 입출력) | DB 컬럼 정의 X |
| `app/api/` | HTTP 라우터만. 비즈니스 로직은 services 호출 | SQL 직접 작성 X |
| `app/services/news_collector.py` | RSS 수집만 | DB·LLM 호출 X |
| `app/services/llm_processor.py` | Gemini 호출 + 프롬프트만 | DB 호출 X |
| `app/services/news_repository.py` | DB CRUD만 | LLM·RSS 호출 X |
| `app/core/logger.py` | 로깅 설정 | |
| `app/core/exceptions.py` | 커스텀 예외 | |

## "X를 바꾸려면 어디?" 빠른 찾기

| 바꾸고 싶은 것 | 손댈 파일 |
|--------------|----------|
| RSS 소스 추가/변경 | `app/services/news_collector.py` → `SOURCES` 리스트 |
| Gemini 프롬프트 수정 | `app/services/llm_processor.py` → `SYSTEM_INSTRUCTION`, `USER_PROMPT_TEMPLATE` |
| Gemini 모델 변경 | `.env` → `GEMINI_MODEL`. 코드 변경 불필요 |
| DB 컬럼 추가 | `app/models/news.py` 수정 + 마이그레이션 |
| API 응답 형식 바꾸기 | `app/schemas/news.py` |
| 정렬 기준 바꾸기 (중요도·시간 등) | `app/services/news_repository.py` → `get_today_top` |
| 새 API 엔드포인트 추가 | `app/api/` 안에 새 라우터 → `main.py`에 include |
| cron 시간 변경 | `.github/workflows/daily-fetch.yml` → `schedule.cron` |
| 환경변수 추가 | `app/config.py` + `.env.example` 둘 다 |

## 의존 방향 규칙 (지키지 않으면 유지보수 망함)

```
api  →  services  →  models / repository
 ↓        ↓
schemas  core (logger, exceptions, config)
```

- 위에서 아래로만 import. 반대 방향 금지.
- `services`가 `api`를 import? → 잘못된 구조.
- `models`가 `services`를 import? → 잘못된 구조.

## 데이터 모델

`News` 테이블 한 개. 컬럼 의미:

| 컬럼 | 의미 | 단계 |
|------|------|------|
| `source`, `title`, `url`, `raw_summary`, `published_at` | RSS 수집 직후 채워짐 | 1단계 |
| `summary`, `context`, `importance`, `tags`, `processed_at` | Gemini 처리 후 채워짐 | 2단계 |

`processed_at IS NULL` = 아직 LLM 처리 안 됨. 다음 cron에서 다시 시도.

## v0.1 한계 (알아두기)

- **Render 무료의 영구 저장 없음**: SQLite를 `/tmp`에 둠 → 서버 재시작 시 데이터 사라짐. v0.1엔 OK (매일 새로 수집). v0.2에서 PostgreSQL 또는 Supabase로 이전.
- **Render 무료의 sleep**: 15분 무요청 시 sleep. 첫 요청 30초~1분 지연. GitHub Actions cron이 깨워줌.
- **Gemini 무료 RPD 한도**: Flash-Lite 1500/일. 뉴스 50개 × 1 call = 50 call/day → 여유 있음. 프롬프트 튜닝 중엔 캐싱·더미 활용.
- **푸시 알림 없음**: v0.2에서 FCM 추가.
- **개인화 없음**: v0.2에서 사용자 관심 종목/섹터 기반 필터.

## 로컬 실행

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp ../.env.example ../.env
# .env 파일 열어서 GEMINI_API_KEY 채우기

uvicorn main:app --reload
# → http://localhost:8000/docs 에서 Swagger UI 확인

# 수동으로 fetch 트리거
curl -X POST http://localhost:8000/admin/fetch \
  -H "Authorization: Bearer dev-only-change-me"

# 뉴스 조회
curl http://localhost:8000/news/today
```

## Render 배포

1. GitHub에 push.
2. Render 대시보드 → New → Blueprint → 본인 레포 선택.
3. `backend/render.yaml`이 자동 감지됨.
4. `GEMINI_API_KEY` 환경변수만 수동 입력 (sync: false라 자동 안 됨).
5. 배포 후 URL 확인 (예: `https://fingate-backend.onrender.com`).

## GitHub Actions cron 활성화

레포 Settings → Secrets and variables → Actions → New secret:

- `BACKEND_URL` = Render에서 발급된 URL (끝에 슬래시 없이)
- `ADMIN_TOKEN` = Render 대시보드에서 자동 생성된 ADMIN_TOKEN 값

## 다음 단계 (v0.2 예정)

- 해외 뉴스 추가 (Bloomberg/Reuters/WSJ RSS)
- PostgreSQL 이전
- 사용자 인증 + 관심 종목 설정
- FCM 푸시 알림 (중요도 5 뉴스만)
- Flutter 앱 v0.1
