# Spring–AI 카드뉴스 제작 API 계약

이 문서는 BE 연동 검토용 초안입니다. Spring이 작업 ID를 발급해 AI 서버에 제작 작업을 등록하고, 같은 ID로 상태와 결과를 조회합니다.

## 작업 등록

`POST /api/v1/internal/jobs`

| 필드 | 타입 | 조건 |
| --- | --- | --- |
| `jobId` | 문자열 | 필수. Spring이 발급한 작업 ID |
| `domain` | 문자열 | 필수. 초기 지원 분야는 `economy` |
| `templateId` | 문자열 | 필수. 사용자가 선택한 템플릿 ID |

`jobId`와 `templateId`는 영문자 또는 숫자로 시작하는 1~128자 식별자입니다. 이후에는 영문자, 숫자, 하이픈, 밑줄을 사용할 수 있습니다.

```json
{
  "jobId": "job-001",
  "domain": "economy",
  "templateId": "economy-brief-v1"
}
```

새 작업을 접수하면 `202 Accepted`와 접수 상태를 반환합니다.

```json
{
  "isSuccess": true,
  "code": "JOB_ACCEPTED",
  "message": "제작 작업을 접수했습니다.",
  "result": {"jobId": "job-001", "status": "queued"},
  "error": null
}
```

동일한 ID와 입력으로 재요청하면 `200 OK` 및 `JOB_EXISTS`와 기존 작업의 현재 상태를 반환합니다. 같은 ID에 입력이 다르면 `409 Conflict` 및 `JOB_ID_CONFLICT`를 반환합니다.

## 작업 조회

`GET /api/v1/internal/jobs/{jobId}`

| 작업 상태 | `result`의 정보 |
| --- | --- |
| `queued` | 작업 접수 상태 |
| `running` | 실행 중인 단계 `stage` |
| `succeeded` | 카드 순서와 이미지 URL, 캡션, 출처가 담긴 `output` |
| `failed` | 실패 단계, 오류 코드, 메시지가 담긴 `failure` |

조회에 성공하면 HTTP `200 OK`, `isSuccess: true`, `code: "JOB_FOUND"`를 반환합니다. 카드뉴스 제작에 실패했을 때는 `result.status`가 `failed`입니다. 상태에 해당하지 않는 `stage`, `output`, `failure` 필드는 `null`입니다.

실행 중 조회 응답

```json
{
  "isSuccess": true,
  "code": "JOB_FOUND",
  "message": "제작 작업을 조회했습니다.",
  "result": {
    "jobId": "job-001",
    "status": "running",
    "stage": "sample",
    "output": null,
    "failure": null
  },
  "error": null
}
```

완료 후 조회 응답

```json
{
  "isSuccess": true,
  "code": "JOB_FOUND",
  "message": "제작 작업을 조회했습니다.",
  "result": {
    "jobId": "job-001",
    "status": "succeeded",
    "stage": null,
    "output": {
      "cards": [
        {"order": 1, "imageUrl": "http://127.0.0.1:8000/api/v1/internal/sample-cards/card-01.jpg"},
        {"order": 2, "imageUrl": "http://127.0.0.1:8000/api/v1/internal/sample-cards/card-02.jpg"},
        {"order": 3, "imageUrl": "http://127.0.0.1:8000/api/v1/internal/sample-cards/card-03.jpg"},
        {"order": 4, "imageUrl": "http://127.0.0.1:8000/api/v1/internal/sample-cards/card-04.jpg"},
        {"order": 5, "imageUrl": "http://127.0.0.1:8000/api/v1/internal/sample-cards/card-05.jpg"}
      ],
      "caption": "ReelCrew 제작 API 연동용 샘플 카드뉴스입니다.",
      "sources": [{"title": "예시 경제 자료", "url": "https://example.com/economy"}]
    },
    "failure": null
  },
  "error": null
}
```

작업 실패 후 조회 응답

```json
{
  "isSuccess": true,
  "code": "JOB_FOUND",
  "message": "제작 작업을 조회했습니다.",
  "result": {
    "jobId": "job-001",
    "status": "failed",
    "stage": null,
    "output": null,
    "failure": {
      "stage": "sample",
      "code": "SAMPLE_CARD_UNAVAILABLE",
      "message": "샘플 카드 파일을 사용할 수 없습니다."
    }
  },
  "error": null
}
```

## API 오류

| HTTP 상태 | `code` | 조건 |
| --- | --- | --- |
| `422 Unprocessable Content` | `INVALID_REQUEST` | 요청 JSON 또는 필드 형식 오류 |
| `404 Not Found` | `JOB_NOT_FOUND` | 조회할 작업이 없음 |
| `409 Conflict` | `JOB_ID_CONFLICT` | 동일 작업 ID에 다른 입력을 등록하려고 함 |

API 오류는 `isSuccess: false`와 `result: null`을 반환합니다. 입력 검증 오류에는 `error.details`에 필드와 메시지를 담습니다.

```json
{
  "isSuccess": false,
  "code": "INVALID_REQUEST",
  "message": "제작 작업 요청의 형식이 올바르지 않습니다.",
  "result": null,
  "error": {
    "details": [{"field": "body.templateId", "message": "Field required"}]
  }
}
```

## 샘플 연동

AI 서버는 요청의 호스트를 기준으로 카드 이미지 URL을 반환합니다. Spring은 AI 서버에 접속할 수 있는 주소로 제작 API를 호출한 뒤, 반환된 이미지 URL에서 카드 파일을 읽을 수 있습니다. 프론트엔드에서 접근 가능한 이미지 전달 방식은 BE 연동 시 합의합니다.

작업은 AI 서버 프로세스의 메모리에 저장합니다. 샘플 연동에서는 AI 서버를 단일 프로세스로 실행하고, 서버를 재시작하면 작업을 다시 등록합니다. 모든 템플릿 ID에 공통 샘플 이미지를 반환하며, 출처 값도 응답 형식 확인용입니다.

서버 실행 후 Swagger 문서에서 작업을 등록하고, 반환받은 `jobId`를 조회합니다. 샘플 처리가 빠르므로 첫 조회에서 곧바로 `succeeded`가 반환될 수 있습니다.
