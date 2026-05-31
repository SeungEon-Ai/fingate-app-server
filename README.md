# Fingate

> 매일 쏟아지는 금융 뉴스 중 **뭐가 중요하고 왜 중요한지** 5분 안에.

## 무엇

- RSS로 한국 경제 뉴스 자동 수집
- Gemini 2.5 Flash-Lite로 요약 + 중요도(1~5) + 컨텍스트 생성
- API로 모바일 앱에 전달

## 스택

- **백엔드**: FastAPI + SQLAlchemy + SQLite, Python 3.11
- **LLM**: Google Gemini (무료 티어)
- **호스팅**: Render (백엔드), GitHub Actions (cron)
- **모바일 앱**: Flutter (Android first) — v0.2

## 폴더 구조

```
fingate/
├── backend/           # FastAPI 서버 (Render 배포)
├── mobile/            # Flutter 앱 (v0.2부터)
├── .github/workflows/ # 매일 자동 수집 cron
├── ARCHITECTURE.md    # 코드 수정 시 어디 봐야 하는지
├── .env.example       # 환경변수 템플릿
└── README.md
```

## 시작하기

전체 흐름은 [ARCHITECTURE.md](./ARCHITECTURE.md) 참고. 빠른 로컬 실행:

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
(Root Directory - backend)

cp ../.env.example ../.env
# .env 열어서 GEMINI_API_KEY 입력 (https://aistudio.google.com/apikey)

uvicorn main:app --reload
```

브라우저에서 http://localhost:8000/docs

## API 엔드포인트

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/health` | 헬스체크 | X |
| GET | `/news/today` | 오늘의 뉴스 | X |
| POST | `/admin/fetch` | 수집·처리 트리거 | Bearer 토큰 |

## 로드맵

- **v0.1** (현재): 백엔드 + 한국 RSS + Gemini 요약
- **v0.2**: Flutter Android 앱
- **v0.3**: 해외 뉴스 (Bloomberg/Reuters/WSJ)
- **v0.4**: 사용자 계정 + 관심 종목 필터
- **v0.5**: FCM 푸시 알림
- **v1.0**: Google Play 정식 출시

## 면책

투자 자문 아님. 모든 정보는 참고용. 투자 결정과 그 결과의 책임은 본인.
