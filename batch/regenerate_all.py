# -*- coding: utf-8 -*-
"""
상품 목록이 바뀌면 여기서부터 다시 만든다 — 재생성 파이프라인
================================================================================

왜 스크립트로 묶는가
    상품 200개가 바뀌면 어휘집·친화도·페르소나·성향·평가 정본·서빙 산출물이
    **전부** 따라 바뀐다. 손으로 순서대로 돌리다 하나를 빠뜨리면 파일 사이가
    조용히 어긋난다. 실제로 레포 페르소나가 구버전에 멈춰 있어서, 시뮬레이터가
    읽는 페르소나와 정확도를 측정한 페르소나가 서로 다른 사람이었던 사고가 났다
    (9,900명 중 3,603명만 겹쳤다). 그때는 아무 에러도 나지 않았다.

    그래서 이 스크립트는 **순서를 코드로 고정**하고, 각 단계의 산출물이 실제로
    새로 쓰였는지 mtime 으로 확인한다.

의존 순서 (앞이 뒤의 입력이다)

    1. products_200.json          <- 리뷰 원본 CSV
    2. product-feature-vocab.json <- 1
    3. affinity_lift.csv          <- 1 + 리뷰 원본
    4. concern_from_reviews.npz   <- 1 + 리뷰 원본 (GPU. 임베딩)
    5. personas_9900/100.json     <- 1 + 리뷰 원본
    6. persona_style.json         <- 5
    7. eval_metadata.jsonl        <- 5   (PA 대조군 eval_metadata_agent.jsonl 포함)
    8. feature_sample.json + 문서 <- 1 2 3 4
    9. serving/ (3종)             <- 1 2 3 4 5

    행동 로그 생성(gen_behavior_logs.py)과 PA 에이전트 실행은 이 뒤다.
    이 스크립트는 로그까지는 만들지 않는다 — 시간이 크게 다르고(수십 분),
    수집 API·프론트가 떠 있어야 하기 때문이다.

실행
    SEPHORA_DATASET=/path/to/dataset/sephora python batch/regenerate_all.py
    ... --skip-gpu      4번(임베딩)을 건너뛴다. 기존 npz 를 그대로 쓴다
    ... --from 5        5번부터 (상품은 그대로고 페르소나만 다시 뽑을 때)
    ... --dry-run       무엇을 어떤 순서로 돌릴지만 보여준다

끝나면
    - `python -m pytest batch` 또는 각 test_*.py 로 계약 검증
    - 레포에 커밋 (산출물도 추적 대상이다)
    - 페르소나가 바뀌었으면 **PA 100명 재실행**이 필요하다
"""
import argparse
import os
import subprocess
import sys
import time

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, ".."))
DATA = os.path.join(ROOT, "batch", "ingest", "data")
PERSONA = os.path.join(ROOT, "simulator", "personas", "data")
CONTRACTS = os.path.join(ROOT, "contracts")

# (번호, 이름, 명령, 산출물, GPU 여부)
#   산출물은 mtime 으로 "정말 새로 쓰였는가" 를 본다. 스크립트가 조용히
#   아무것도 안 하고 성공하는 경우를 잡기 위한 것이다.
STEPS = [
    (1, "상품 200개 카탈로그",
     ["batch/ingest/build_products_json.py"],
     [os.path.join(DATA, "products_200.json"),
      os.path.join(DATA, "excluded_products.json")], False),
    (2, "인코딩 어휘집 (148차원)",
     ["batch/ingest/build_feature_vocab.py"],
     [os.path.join(CONTRACTS, "product-feature-vocab.json")], False),
    # 상품 등록 폼이 쓰는 한국어 라벨. 어휘집에서 값을 읽으므로 2번 뒤다
    (2.5, "상품 등록 폼 한국어 라벨",
     ["batch/ingest/build_form_labels.py"],
     [os.path.join(CONTRACTS, "product-form-labels-ko.json")], False),
    (3, "속성 친화도 4,000행",
     ["batch/ingest/build_affinity_lift.py"],
     [os.path.join(DATA, "affinity_lift.csv")], False),
    (4, "리뷰에서 concern 블록",
     ["batch/jobs/concern_from_reviews.py"],
     [os.path.join(DATA, "concern_from_reviews.npz")], True),
    (5, "페르소나 10,000명",
     ["simulator/personas/build_personas.py"],
     [os.path.join(PERSONA, "personas_9900.json"),
      os.path.join(PERSONA, "personas_100_agent.json"),
      os.path.join(PERSONA, "persona_sampling_report.json")], False),
    # 동시발생은 리뷰 원본을 읽으므로 SEPHORA_DATASET 이 필요하다.
    #
    # **자리가 여기인 이유가 둘이다.**
    #   - 앞: 누출 차단이 `personas_*.json` 을 훑어 author_id 를 빼므로 5번 뒤여야
    #     한다. **페르소나 파일이 늘면 반드시 다시 만들어야 한다** — 새 홀드아웃이
    #     동시발생에 남아 있으면 그 홀드아웃으로 잰 수치가 전부 거짓이 된다
    #   - 뒤: 9번의 `ranking_golden.json` 이 CF 항을 포함하므로 **이것보다 먼저
    #     돌면 골든이 조용히 CBF 기준으로 만들어진다.** 자바가 그 골든을 재현하면
    #     검증이 통과해도 서빙이 틀린다
    (5.5, "아이템-아이템 동시발생 (CF 가점 입력)",
     ["batch/jobs/build_cooc.py"],
     [os.path.join(DATA, "serving", "item_cooc.npz")], False),
    (6, "페르소나 성향 6축",
     ["simulator/generator/build_persona_style.py"],
     [os.path.join(PERSONA, "persona_style.json")], False),
    (7, "평가 seed/target 정본",
     ["batch/jobs/eval_metadata.py"],
     [os.path.join(DATA, "eval_metadata.jsonl")], False),
    # PA 100명은 PC 9,900명의 대조군이라 **같은 규칙으로** 만들어야 한다.
    # 여기에 넣어 두지 않으면 PC 만 재생성되고 두 파일의 정의가 갈린다
    (7.5, "평가 seed/target 정본 (PA 100명 대조군)",
     ["batch/jobs/eval_metadata.py", "--agent"],
     [os.path.join(DATA, "eval_metadata_agent.jsonl")], False),
    (8, "인코딩 샘플 6개 + 문서",
     ["batch/ingest/build_feature_sample.py"],
     [os.path.join(DATA, "feature_sample.json")], False),
    # 학습 결합 모델. eval_metadata 의 train 분할과 동시발생을 읽으므로 7·5.5 뒤다.
    # **9번의 골든이 이 모델로 만들어지므로 반드시 그 앞이어야 한다** — 없으면
    # 골든이 조용히 선형 기준으로 나오고, 자바가 그것을 재현하면 서빙이 틀린다.
    (8.5, "학습 결합 모델 (LTR)",
     ["batch/jobs/train_ltr.py"],
     [os.path.join(DATA, "serving", "ltr_model.pkl"),
      os.path.join(DATA, "serving", "ltr_model_meta.json")], False),
    (9, "서빙 산출물 + 순위 대조 기준",
     ["batch/jobs/export_features.py"],
     [os.path.join(DATA, "serving", "product_feature.jsonl"),
      os.path.join(DATA, "serving", "attribute_affinity.csv"),
      os.path.join(DATA, "serving", "ranking_golden.json")], False),
    # 배너 축 목록은 어휘집·친화도·인기도에서 나오므로 그 뒤에 온다.
    # 어휘가 늘었는데 목록을 안 다시 만들면 새 값이 배너에 영영 안 뜬다.
    (10, "배너 축 6종 상품 목록",
     ["batch/jobs/banner_axes.py"],
     [os.path.join(DATA, "serving", "banner_axes.json")], False),
    # 대시보드 파생 산출물. 인코더·친화도·concern 에서 나오므로 그 뒤에 온다.
    (11, "대시보드용 파생 산출물 4종",
     ["batch/jobs/export_dashboard.py"],
     [os.path.join(DATA, "serving", "product_ingredient_position.csv"),
      os.path.join(DATA, "serving", "product_concern_top2.csv"),
      os.path.join(DATA, "serving", "ingredient_skin_lift.csv")], False),
]


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def child_env():
    """자식 프로세스의 출력 인코딩을 UTF-8 로 고정한다.

    윈도우 콘솔은 cp949 라 스크립트가 em dash 하나에 UnicodeEncodeError 로 죽는다.
    실제로 eval_metadata.py 가 여기서 걸렸다. 스크립트마다 고치는 대신 부모가
    환경변수로 한 번에 정한다 (리눅스에서는 무해하다).
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", type=int, default=1,
                    help="이 번호부터 실행한다 (기본 1)")
    ap.add_argument("--to", type=int, default=99, help="이 번호까지")
    ap.add_argument("--skip-gpu", action="store_true",
                    help="임베딩 단계를 건너뛴다. 기존 산출물을 그대로 쓴다")
    ap.add_argument("--dry-run", action="store_true", help="순서만 보여준다")
    a = ap.parse_args()

    todo = [s for s in STEPS if a.start <= s[0] <= a.to
            and not (a.skip_gpu and s[4])]
    if not todo:
        raise SystemExit("실행할 단계가 없습니다.")

    if not os.environ.get("SEPHORA_DATASET") and any(s[0] in (1, 3, 4, 5, 5.5) for s in todo):
        raise SystemExit(
            "SEPHORA_DATASET 환경변수가 필요합니다 (1·3·4·5·5.5 단계가 리뷰 원본을 읽습니다).\n"
            "  예) SEPHORA_DATASET=.../Research/dataset/sephora python batch/regenerate_all.py")

    print("=" * 72)
    print(f"재생성 {len(todo)}단계" + ("  [dry-run]" if a.dry_run else ""))
    for n, name, cmd, outs, gpu in todo:
        print(f"  {n}. {name}{'  (GPU)' if gpu else ''}")
        print(f"       {' '.join(cmd)}")
    print("=" * 72)
    if a.dry_run:
        return

    t_all = time.time()
    for n, name, cmd, outs, gpu in todo:
        before = {p: (os.path.getmtime(p) if os.path.exists(p) else 0) for p in outs}
        print(f"\n[{n}/{len(STEPS)}] {name}", flush=True)
        t0 = time.time()
        r = subprocess.run([sys.executable] + cmd, cwd=ROOT, env=child_env())
        if r.returncode != 0:
            print(f"\n  ✗ {n}번에서 멈췄습니다 (종료 코드 {r.returncode}).")
            print("    뒤 단계는 앞 단계의 산출물을 읽으므로 여기서 중단합니다.")
            raise SystemExit(r.returncode)
        # 성공했다는데 파일이 그대로면 조용한 실패다. 반드시 잡는다
        stale = [p for p in outs
                 if not os.path.exists(p) or os.path.getmtime(p) <= before[p]]
        if stale:
            print(f"\n  ✗ 성공했다는데 산출물이 새로 쓰이지 않았습니다:")
            for p in stale:
                print(f"      {rel(p)}")
            print("    스크립트가 조용히 아무것도 안 했을 수 있습니다. 확인하십시오.")
            raise SystemExit(1)
        print(f"  ✓ {time.time() - t0:.0f}초 · " +
              " · ".join(f"{rel(p)} {os.path.getsize(p)/1024:,.0f}KB" for p in outs))

    print("\n" + "=" * 72)
    print(f"전체 {time.time() - t_all:.0f}초")
    print("다음으로 할 것")
    print("  1. 계약 검증 —  python batch/jobs/test_eval_metadata.py 등 test_*.py")
    print("  2. 산출물 커밋 — 페르소나·상품 파일도 추적 대상입니다")
    print("  3. 페르소나가 바뀌었으면 PA 100명 재실행이 필요합니다")
    print("     (simulator/agents/README.md)")
    print("=" * 72)


if __name__ == "__main__":
    main()
