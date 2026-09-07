# 계약 디렉터리 기준

`contracts/`는 서비스·수집·데이터 처리·추천 구성요소가 함께 준수해야 하는 확정
데이터 계약의 단일 위치다. 코드에서 직접 검증하는 JSON뿐 아니라 grain, key,
nullable 및 입출력 구조를 정의하는 Markdown 명세도 이 디렉터리에서 관리한다.

## 파일 역할

| 유형 | 역할 | 예시 |
| --- | --- | --- |
| 실행 계약 | validator나 테스트가 직접 읽는 Schema·vocabulary | `event-schema.json`, `product-feature-vocab.json` |
| 명세 계약 | 여러 구성요소가 합의한 grain, key, field 및 처리 경계 | `processed-schema.md`, `recommendation-io-spec.md` |
| 정상·오류 샘플 | 계약 통과 payload와 의도적인 위반 payload | `samples/` |
| 검증 코드 | 계약 위반과 구현 drift를 탐지 | `validate_events.py`, `coverage_report.py`, `tests/` |

`docs/analytics/`는 계약을 선택한 이유, 처리 흐름, 구현 현황, KPI 해석 및 검증 계획을
설명한다. 동일한 컬럼·enum·산식을 두 위치에 각각 원본으로 복제하지 않는다. 설명
문서와 계약이 충돌하면 `contracts/`의 해당 계약을 우선한다.

## 현재 단일 출처

| 범위 | 단일 출처 |
| --- | --- |
| Raw Event 공통 Envelope·event enum·synthetic 필수 metadata | `event-schema.json` |
| Event별 intent 의미·properties·property enum | `event-properties-schema.md` |
| 통합몰 business·brand·product Event 귀속·영향 범위 | `event-attribution-contract.md` |
| Raw Dataset grain·물리 key·컬럼·타입·nullable·partition | `raw-event-schema.md` |
| Processed Dataset grain·key·컬럼·타입·nullable·partition | `processed-schema.md` |
| Persona·리뷰·평가 split·segment·Simulation Run | `persona-schema.md` |
| DW Dimension·Mart grain·key·컬럼·타입·nullable | `dw-schema.md` |
| Product Feature | `product-feature-spec.md`, `product-feature-vocab.json` |
| 상품 등록 입력 필드·어휘 제약·파생값 | `product-registration-spec.md` |
| 상품 등록 폼 어휘와 한국어 표시 문구 | `product-form-labels-ko.json` |
| Recommendation 입출력과 행동 집계 | `recommendation-io-spec.md` |

`product-form-labels-ko.json`은 `batch/ingest/build_form_labels.py`가 어휘집에서
생성한다. 직접 편집하지 않는다.

## 변경 규칙

1. 계약 변경 MR은 관련 구현과 검증 샘플 또는 drift 검증 결과를 함께 갱신한다.
2. 하위 호환되지 않는 필드 삭제·이름 변경·타입 변경·필수 전환은 Schema version
   변경 여부를 검토한다.
3. 설명만 바뀌는 경우 계약을 수정하지 않는다.
4. 계약이 바뀌는 경우 관련 설명 문서는 계약을 복사하지 않고 변경된 계약을
   참조하도록 갱신한다.

## 검증 명령

### Event

```bash
python contracts/validate_events.py contracts/samples/raw-event.user.valid.json
python contracts/coverage_report.py contracts/samples/event-properties.valid.json
python contracts/coverage_report.py contracts/samples/event-properties.invalid.json
```

마지막 명령은 의도적인 required property·타입·enum 위반을 탐지하므로 종료 코드 2가
정상이다.

### 상품 등록

```bash
python contracts/validate_product_registration.py <상품 JSON 또는 JSONL>
```

**등록 입력에만 사용한다.** 기존 카탈로그 `products_200.json`은 Sephora 원천이라
`highlights`에 성분 태그가 남아 있어 `product-registration-spec.md` §3.1 위반으로
잡힌다. 인코더는 그 태그를 쓰지 않으므로 결함이 아니며, 앞으로 무엇을 받을지에 대한
규칙과 과거 데이터의 차이일 뿐이다.

### Persona

```bash
python contracts/persona/validate_persona_tables.py contracts/persona/data
python contracts/persona/compare_holdout_rules.py --require-zero
```
