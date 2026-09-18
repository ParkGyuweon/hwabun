# 추천 추론 서버 (FastAPI, 계약 §5·§5-1·§5-2) — Jira 219
#
# 빌드 (레포 루트가 컨텍스트, BuildKit 필수 — 옆의 recommend.Dockerfile.dockerignore 를 쓴다):
#   DOCKER_BUILDKIT=1 docker build -f deploy/recommend.Dockerfile -t hwabun-recommend .
# 실행:
#   docker run -p 8300:8300 -v recommend-data:/data hwabun-recommend
#   curl localhost:8300/health
#
# 이미지가 들고 가는 것 — 서버가 기동 때 읽는 파일 전부 (Engine.__init__ 기준):
#   batch/jobs·batch/serving           코드
#   batch/ingest/data/products_200.json · concern_from_reviews.npz · affinity_lift.csv · eval_metadata*.jsonl
#   batch/ingest/data/serving/          모델(ltr_model.pkl)·친화도·CF·배너 축·등록 상품 시드
#   contracts/                          어휘집·등록 검증기 (validate_product_registration.py 가 vocab·labels 를 읽는다)
#   simulator/personas/data/personas_*.json   페르소나 12,000명 (속성 친화도 입력, ~84MB)
#   frontend/src/types/log.ts           행동 가중치의 단일 소스 (behavior_weights.py 가 직접 읽는다)
#   simulator/feedback/banned_terms.py  처방 문장 금지어 검사 (Jira 220, contracts/feedback-banned-terms.json 과 함께)
#
# 등록 상품(POST /api/products)은 /data/registered_products.jsonl 에 쌓인다 — 볼륨으로 두어
# 컨테이너를 갈아도 남게 한다. 첫 기동에 이미지 안의 시드(SSAFY Beauty 8개)를 복사한다.

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8300 \
    REGISTERED_PRODUCTS_PATH=/data/registered_products.jsonl

WORKDIR /app

# 의존성 먼저 — 코드가 바뀌어도 이 레이어는 캐시된다. sklearn 버전은 pickle 과 맞아야 한다
COPY batch/serving/requirements.txt /app/batch/serving/requirements.txt
RUN pip install --no-cache-dir -r /app/batch/serving/requirements.txt

# 코드 + 산출물. 경로를 레포와 같게 두어 모듈의 ROOT 상대 경로가 그대로 맞는다
COPY batch/jobs/            /app/batch/jobs/
COPY batch/serving/         /app/batch/serving/
COPY batch/ingest/data/products_200.json \
     batch/ingest/data/concern_from_reviews.npz \
     batch/ingest/data/affinity_lift.csv \
     batch/ingest/data/eval_metadata.jsonl \
     batch/ingest/data/eval_metadata_agent.jsonl \
     batch/ingest/data/eval_metadata_holdout_a.jsonl \
     batch/ingest/data/eval_metadata_holdout_b.jsonl \
                            /app/batch/ingest/data/
COPY batch/ingest/data/serving/ /app/batch/ingest/data/serving/
COPY contracts/             /app/contracts/
COPY simulator/personas/data/personas_9900.json \
     simulator/personas/data/personas_100_agent.json \
     simulator/personas/data/personas_holdout_a.json \
     simulator/personas/data/personas_holdout_b.json \
                            /app/simulator/personas/data/
COPY frontend/src/types/log.ts /app/frontend/src/types/log.ts
# /live 시연 구동 (Jira 295·335): 시작 버튼이 demo_live.py 를 자식 프로세스로 띄우고, 캐시가 없으면
# gen_behavior_logs.py 로 9,900명 로그를 만든다. 이 파일들이 없어 배포본에서 404 DEMO_UNAVAILABLE 이었다(09-16).
COPY simulator/generator/demo_live.py      simulator/generator/gen_behavior_logs.py      simulator/generator/recommend_client.py                             /app/simulator/generator/
COPY simulator/personas/data/persona_style.json /app/simulator/personas/data/persona_style.json
COPY frontend/src/mocks/products.sample.json      frontend/src/mocks/products.ssafy-beauty.json                             /app/frontend/src/mocks/
COPY simulator/feedback/banned_terms.py      simulator/feedback/classify_feedback.py                             /app/simulator/feedback/
COPY deploy/recommend-entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && mkdir -p /data

VOLUME ["/data"]
EXPOSE 8300

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8300/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/app/entrypoint.sh"]
