# ReelCrew AI

ReelCrew의 AI 백엔드입니다. 카드뉴스 제작 요청을 받아 자료 조사, 원고 작성, 이미지 렌더링 결과를 서비스 백엔드에 전달하는 서버를 개발합니다.

## 로컬 실행

[uv](https://docs.astral.sh/uv/getting-started/installation/)를 설치한 뒤 레포 루트에서 실행합니다.

```bash
uv sync --locked
uv run --locked fastapi dev app/main.py
```

기본 주소는 `http://127.0.0.1:8000`입니다. [API 문서](http://127.0.0.1:8000/docs)에서 `GET /health`를 호출하거나 다음 명령을 실행합니다.

```bash
curl -fsS http://127.0.0.1:8000/health
```

정상 응답은 `{"status":"ok"}`입니다.

`app/main.py`는 FastAPI 앱의 진입점입니다. Python 버전은 `.python-version`에서, 의존성은 `pyproject.toml`과 `uv.lock`에서 관리합니다.
