# batch/ingest — 데이터 빌드 스크립트

산출물 설명은 [`data/README.md`](data/README.md)(입력·중간 산출물) 와 [`data/serving/README.md`](data/serving/README.md)(서버가 읽는 것).

| 스크립트 | 만드는 것 |
|---|---|
| `build_feature_vocab.py` | `contracts/product-feature-vocab.json` (어휘집 0.5) · 폼 라벨 |
| `build_affinity_lift.py` | `data/affinity_lift.csv` (속성 × 상품 친화도, 리뷰 844,865건) |
| `build_reviews_100.py` | 상품당 리뷰 100건 층화 추출 (원천 458,217건, 평균 = 화면 별점 200/200) — 2026-09-10 |
| `merge_reviews_ko.py` | 번역본 검수 A~G → `contracts/localization/reviews-ko.json` (20,000건, `--allow` 로 사람이 본 id 통과) |
| `build_reviews_ko_files.py` | 프론트가 fetch 하는 상품별 한국어 리뷰 파일 200개 |
| `build_ko_catalog.py` · `polish_korean_catalog.py` | 상품·라벨 한국어화 JSON |
| 그 외 `build_*.py` | 골든·배너 축·대시보드·백엔드 테이블 (전체 재생성은 `batch/regenerate_all.py`) |

`build_reviews_100.py` 의 원천 경로 기본값은 로컬 개인 폴더(`Research/dataset/sephora`)라 env 로 덮어써야 다른 PC 에서 돈다.
