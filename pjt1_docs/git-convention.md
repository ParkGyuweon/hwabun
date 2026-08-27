# Git 커밋 및 브랜치 컨벤션

## 1. 브랜치 전략

| 브랜치 | 역할 |
|---|---|
| `master` | 배포·최종 안정 버전. **직접 push 금지** |
| `dev` | 개발 기능을 통합하는 기준 브랜치 |
| 작업 브랜치 | `dev`에서 분기. 기능 단위로 생성 |

### 작업 시작 전 최신화

```bash
git switch dev
git pull origin dev
git switch -c 브랜치명
```

### 작업 완료 후

**`dev`를 대상으로** Merge Request를 생성합니다. Assignee는 `Assign to me`로 본인을 지정합니다.

---

## 2. 커밋 메시지 형식

```
type(scope): 작업 내용
```

- `type` — 어떤 종류의 작업인지 표시
- `scope` — 작업한 영역 표시
- `작업 내용` — 실제로 변경한 내용

## 3. Type 종류

| Type | 사용 상황 |
|---|---|
| `feat` | 새로운 기능 추가 |
| `fix` | 오류 또는 버그 수정 |
| `refactor` | 기능 변화 없이 코드 구조 개선 |
| `docs` | README, 기획서 등 문서 수정 |
| `test` | 테스트 코드 작성 및 수정 |
| `style` | 들여쓰기, 공백, 주석 등 코드 형식 수정 |
| `chore` | 설정, 패키지, 폴더 구조 등 기타 작업 |
| `perf` | 성능 개선 |
| `merge` | 브랜치 병합 |

## 4. Scope 예시

```
ai        hardware      embedded      server
frontend  database      docs          common
```

프로젝트 상황에 맞게 필요한 항목만 사용합니다.

## 5. 작성 규칙

- 작성자 이름은 커밋 메시지에 **넣지 않습니다**
- 한 커밋에는 **하나의 작업만** 포함합니다
- `수정`, `업데이트`처럼 모호하게 작성하지 않습니다
- 무엇을 변경했는지 **구체적으로** 작성합니다
- 메시지 마지막에는 마침표를 붙이지 않습니다
- 커밋 메시지는 **한국어로 통일**합니다

## 6. 작성 예시

### 올바른 예시

```
feat(ai): 점자블록 객체 탐지 기능 추가
feat(hardware): 카메라 촬영 기능 구현
fix(embedded): 센서 데이터 수신 오류 수정
fix(server): 이미지 업로드 실패 문제 수정
refactor(ai): 이미지 전처리 코드 분리
docs(plan): 프로젝트 기획서 내용 수정
docs(readme): 실행 방법 추가
chore(common): 프로젝트 폴더 구조 정리
```

### 잘못된 예시

```
강하린_코드수정          <- 작성자 이름
경연_업데이트            <- 작성자 이름 + 모호함
feat: 수정               <- scope 없음, 모호함
작업 완료                <- 형식 없음
최종 수정                <- 모호함
진짜 최종 수정           <- 모호함
```

## 7. 평가 자료 업로드 시

```
chore: upload weekly progress and learning logs (번호)
```

---

## 8. 참고 — 본 저장소의 커밋 이력 예시

```
docs(ai): Product Feature 후보표 및 Encoding 초안 작성
docs(ai): skin_fit을 콘텐츠 벡터에서 속성 친화도 테이블로 이관
docs(ai): Attribute Affinity PoC 및 Feature 계산 샘플 추가
docs(ai): 추천 입출력 데이터 구조 문서 추가 및 설계안 이관
chore(ai): 상품 및 페르소나 데이터를 batch, simulator 폴더로 배치
fix(ai): 페르소나 hair_color의 brunette을 brown으로 병합
```

본문이 필요한 경우 제목 아래 빈 줄을 두고 작성합니다. 무엇을 왜 바꿨는지, 수치가 달라졌다면 그 값을 함께 남깁니다.

```
fix(ai): 페르소나 hair_color의 brunette을 brown으로 병합

brunette은 brown의 표기 변형(수집 배치별 라벨 차이)이다. 속성 친화도
테이블에는 병합이 반영되어 있었으나 페르소나 파일에는 남아 있어,
해당 페르소나 115명의 hair_color 조회가 실패하던 문제를 해결한다.

- personas_9900.json, personas_100_agent.json 재생성 (seed=42 동일)
- brown 4,733 -> 4,846명, brunette 113 -> 0명
```
