# 계약 디렉터리 기준

`contracts/`는 서비스·수집·데이터 처리·추천 구성요소가 함께 준수해야 하는 확정
데이터 계약의 단일 위치다. 코드에서 직접 검증하는 JSON뿐 아니라 grain, key,
nullable 및 입출력 구조를 정의하는 Markdown 명세도 이 디렉터리에서 관리한다.

## 파일 역할

| 유형 | 역할 | 예시 |
| --- | --- | --- |
| 실행 계약 | validator나 테스트가 직접 읽는 Schema·vocabulary | `event-schema.json`, `product-feature-vocab.json` |
| 명세 계약 | 여러 구성요소가 합의한 grain, key, field 및 처리 경계 | `processed-schema.md`, `recommendation-io-spec.md` |
| 정상 샘플 | 실행 계약을 만족하는 대표 payload | `samples/` |
| 검증 코드 | 계약 위반과 구현 drift를 탐지 | `validate_events.py`, `tests/` |

`docs/analytics/`는 계약을 선택한 이유, 처리 흐름, 구현 현황, KPI 해석 및 검증 계획을
설명한다. 동일한 컬럼·enum·산식을 두 위치에 각각 원본으로 복제하지 않는다. 설명
문서와 계약이 충돌하면 `contracts/`의 해당 계약을 우선한다.

## 현재 단일 출처

| 범위 | 단일 출처 |
| --- | --- |
| Raw Event 공통 Envelope·event enum·synthetic 필수 metadata | `event-schema.json` |
| Product Feature | `product-feature-spec.md`, `product-feature-vocab.json` |
| Recommendation 입출력과 행동 집계 | `recommendation-io-spec.md` |

Event별 `properties`와 Trigger는 현재
`docs/analytics/event-taxonomy-trigger-schema.md`에 남아 있는 전환 예외다. 해당
명세를 `contracts/`로 분리하기 전까지 `event-schema.json`과 함께 확인하며, 두 파일이
충돌하면 실행 검증 범위에서는 `event-schema.json`을 우선한다.

Processed Dataset의 grain·key·컬럼·타입·nullable·partition은 현재
`docs/analytics/processed-schema.md`에 계약과 설계 설명이 함께 있는 전환 예외다.
계약 부분을 `contracts/processed-schema.md`로 분리하고 기존 참조를 갱신한 뒤 이 표의
단일 출처로 등록한다.

## 변경 규칙

1. 계약 변경 MR은 관련 구현과 검증 샘플 또는 drift 검증 결과를 함께 갱신한다.
2. 하위 호환되지 않는 필드 삭제·이름 변경·타입 변경·필수 전환은 Schema version
   변경 여부를 검토한다.
3. 설명만 바뀌는 경우 계약을 수정하지 않는다.
4. 계약이 바뀌는 경우 관련 설명 문서는 계약을 복사하지 않고 변경된 계약을
   참조하도록 갱신한다.
