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

## 개발 계획

첫 시연에서는 고정된 경제 기사 1건과 템플릿 1종을 사용해 카드 이미지 5장, 캡션, 출처를 생성합니다. 서비스 백엔드를 통해 프론트엔드에서 결과를 미리볼 수 있는 상태를 목표로 합니다.

### Spring과 AI 서버의 연동

Spring이 제작 작업 ID를 발급하고, FastAPI에 내부 HTTP API로 요청합니다. AI 서버는 작업을 접수한 뒤 제작을 실행하며, Spring은 같은 ID로 진행 상태와 결과를 조회합니다.

| API 계약 초안 | 주고받는 정보 |
| --- | --- |
| `POST /api/v1/internal/jobs` | Spring이 `jobId`, `domain`, `templateId`를 전달합니다. AI 서버는 접수한 작업의 ID와 상태를 `202 Accepted`로 반환합니다. |
| `GET /api/v1/internal/jobs/{jobId}` | AI 서버가 `queued`, `running`, `succeeded`, `failed` 중 현재 상태를 반환합니다. 실행 중에는 현재 단계, 성공 시에는 카드 이미지 URL·순서·캡션·출처, 실패 시에는 실패 단계와 오류 코드를 전달합니다. |

요청·성공·실패 예제 JSON과 이미지 전달 방식은 [Spring–AI API 계약 초안](docs/spring-ai-api-contract.md)을 기준으로 합의합니다. 동일한 작업 ID와 입력으로 접수 요청이 반복되면 기존 작업을 반환하도록 규칙을 정합니다. Spring은 제작 결과를 프론트엔드에 전달하고 사용자 승인과 Instagram 게시를 담당합니다.

### 첫 통합 시연

1. API 계약을 정한 뒤 FastAPI에 작업 등록·조회 API를 추가합니다. 샘플 이미지·캡션·출처를 반환해 프론트엔드에서 제작을 요청하고 결과를 미리볼 수 있는지 확인합니다.
2. LangGraph의 상태와 각 단계의 입출력을 정의합니다. 자료, 카드 원고, 렌더링 결과, 검토 결과를 구분하고, 카드 ID와 출처 ID로 연결합니다. 원고 작성과 렌더링 담당 코드가 공통 예제 JSON을 사용합니다.
3. 고정 기사에서 제목·본문·캡션을 생성합니다. 첫 시연에서는 Planning과 Script를 한 번의 외부 LLM 호출로 처리하고, Pydantic으로 카드 수와 출력 형식을 검사합니다.
4. 기존 Pillow 예제를 바탕으로 고정 템플릿 렌더러를 구현합니다. 한글 줄바꿈과 글자 영역을 검사하고, 원고가 넘치면 해당 카드 ID를 반환합니다.
5. LangGraph에서 기사 입력 → 원고 작성 → 렌더링 → 검토 → 결과 저장을 연결합니다. 샘플 API 응답을 실제 제작 결과로 바꾸고, Spring을 거쳐 프론트엔드에 카드 5장·캡션·출처가 표시되는지 확인합니다.

샘플 API 연동과 그래프 상태 설계는 API 계약을 정한 뒤 병행할 수 있습니다. 원고 생성과 렌더러는 공통 카드 명세를 바탕으로 각각 구현한 뒤 그래프에서 연결합니다.

### 자동 수집과 재실행

1. 경제 RSS 피드 한 곳을 연결합니다. 기사 목록의 중복을 제거하고, 선정한 기사의 자료를 확보해 기존 제작 그래프에 전달합니다.
2. 자료 부족, 원고 형식 오류, 외부 호출 실패에 따라 추가 조사·재요청·실패 종료로 분기합니다. 재시도 한도를 정하고, 한도를 넘으면 Spring에서 실패 원인을 조회할 수 있도록 합니다.
3. 글자가 넘친 카드의 문구를 줄이고 해당 카드만 다시 렌더링합니다. 2번 카드에서만 문제가 발생한 입력으로 나머지 카드 이미지가 재사용되는지 확인합니다.
4. 같은 원고와 글자 넘침 조건에서 전체 카드 재제작과 일부 카드 재제작을 비교합니다. 재제작한 카드 수, LLM 호출 수, 처리 시간을 기록합니다.

집중 개발 기준으로 첫 통합 시연에 약 1~2주, 자동 수집·분기·일부 재제작·비교 검증에 추가 1~2주를 예상합니다. 독립 팩트체크, 차트, 학교 GPU 실험, 영상 제작은 후속 범위로 둡니다.

## 컨벤션

<details>

<summary>코드 컨벤션</summary>

### 네이밍과 모듈 구조

- Python 모듈, 함수, 변수는 `snake_case`, 클래스는 `PascalCase`, 상수는 `UPPER_SNAKE_CASE`로 작성합니다.
- 이름에는 역할을 드러내는 단어를 사용합니다. 예를 들어 작업 조회 함수는 `get_job`, 요청 모델은 `JobRequest`로 작성합니다.
- `app/main.py`에서 FastAPI 앱과 라우터를 연결합니다. `app/api/routes/`는 HTTP 요청·응답을 처리하고, `app/services/`는 작업 상태 관리와 제작 로직을 담당합니다. 요청·응답용 Pydantic 모델은 `app/schemas/`에 둡니다.
- API 입출력과 서비스 함수의 인자·반환값에 타입을 명시합니다.
- 의존성을 변경할 때는 `uv add` 또는 `uv remove`를 사용하고, `pyproject.toml`과 `uv.lock`의 변경을 함께 커밋합니다.

### Spring–AI API

- Spring 연동 API는 `/api/v1/internal/` 아래에 둡니다. 여러 단어로 된 경로는 `/api/v1/internal/sample-cards`처럼 하이픈으로 연결합니다.
- Python 모델 필드는 `job_id`처럼 `snake_case`로 작성하고, Pydantic 별칭으로 JSON 계약의 `jobId`를 유지합니다.
- 제작 작업 API는 `ApiResponse[T]`를 사용합니다. 공통 응답 필드는 `isSuccess`, `code`, `message`, `result`, `error`입니다. API 오류는 HTTP 상태 코드와 오류 코드를 함께 반환하고, 제작 작업 자체의 실패는 조회 응답의 `result.status`와 `result.failure`에 담습니다.
- 요청·응답 필드, 상태 코드 또는 오류 코드를 변경할 때는 BE 담당자와 확인하고 문서와 JSON 예시도 함께 갱신합니다. [Spring–AI API 계약 초안](docs/spring-ai-api-contract.md)

</details>

<details>

<summary>Git·이슈·PR 컨벤션</summary>

### 브랜치

- `develop`은 기본 브랜치이자 개발 통합 브랜치입니다. 이슈를 먼저 만든 뒤 최신 `develop`에서 작업 브랜치를 만들고, `develop`으로 PR을 엽니다.
- `main`은 배포용 브랜치입니다. 배포할 때는 `develop`에서 `main`으로 PR을 열어 병합합니다. `main`에 직접 푸시하지 않습니다.
- 작업 브랜치는 `타입/#이슈번호-설명` 형식을 사용합니다. 설명은 영문 소문자와 하이픈으로 작성하고, 명령어에서는 `#`이 들어간 브랜치명을 따옴표로 감쌉니다.

```bash
git switch -c 'feature/#12-card-renderer'
```

### 작업 유형

| 이슈·PR 제목 | 커밋 유형 | 브랜치 접두사 | 용도 |
| --- | --- | --- | --- |
| `FEAT` | `feat` | `feature` | 기능 추가 |
| `FIX` | `fix` | `fix` | 오류 수정 |
| `REFACTOR` | `refactor` | `refactor` | 동작을 유지하는 코드 개선 |
| `TEST` | `test` | `test` | 테스트 추가·수정 |
| `DOCS` | `docs` | `docs` | 문서 추가·수정 |
| `CHORE` | `chore` | `chore` | 설정 및 기타 작업 |
| `BUILD` | `build` | `build` | 빌드 설정과 의존성 변경 |

### 이슈·커밋·PR

| 항목 | 형식 | 예시 |
| --- | --- | --- |
| 이슈 제목 | `[TYPE] 작업 내용` | `[FEAT] 카드 이미지 렌더러 구현` |
| 커밋 메시지 | `type: 작업 내용 (#이슈번호)` | `feat: 카드 이미지 렌더러 구현 (#12)` |
| 작업 PR 제목 | `[TYPE] 작업 내용 (#이슈번호)` | `[FEAT] 카드 이미지 렌더러 구현 (#12)` |

- 이슈에는 작업 배경, 상세 내용, 완료 기준을 적습니다. 오류를 보고할 때는 재현 절차와 기대 결과, 실제 결과를 포함합니다. [이슈 템플릿](.github/ISSUE_TEMPLATE/issue-template.md)
- 커밋 하나에는 하나의 목적을 담습니다. 메시지는 변경 내용을 짧게 적고 끝에 마침표를 붙이지 않습니다.
- PR에는 변경 이유, 주요 변경 사항, 검증 방법과 결과를 적습니다. 카드 이미지나 API 응답이 바뀌면 리뷰에 필요한 예시를 첨부합니다. [PR 템플릿](.github/pull_request_template.md)
- `develop`에 병합하면 완료되는 이슈는 PR 본문에 `Closes #12`처럼 적습니다. 후속 작업이 필요한 이슈는 `#12`처럼 번호를 참조합니다. [GitHub의 이슈 연결 규칙](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue)

</details>
