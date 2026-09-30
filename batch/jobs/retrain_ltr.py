# -*- coding: utf-8 -*-
"""LTR 재학습 경로 — 학습 → holdout_a 비교 → 나쁘지 않으면 교체 → 서버 리로드.

무엇을 하나
    1. `train_ltr.py` 로 후보 모델을 임시 폴더에 만든다 (정본 조건: --seed 1, 가중 코사인 20피처).
    2. `eval_review_replay.py --split holdout_a` 를 **현행 모델과 후보 모델에 각각** 돌려
       Recall@10 을 읽는다. 홀드아웃 체계는 docs/ai/evaluation-framework.md §Q 그대로 —
       고르기는 holdout_a, holdout_b 는 사람이 확인한다.
    3. 후보가 현행보다 `--tolerance`(기본 0.5%p) 넘게 나쁘지 않으면 `--out-dir` 로 옮긴다.
       파일은 임시 이름으로 쓰고 `os.replace` 로 바꿔서 서버가 반쯤 쓰인 pkl 을 읽는 일이 없다.
    4. `--reload-url` 을 주면 `POST /api/model/reload` 로 서버가 재시작 없이 새 모델을 집는다.
    5. 무엇을 했든 `--out-dir/retrain_log.jsonl` 에 한 줄 남긴다 (두 수치·판정·트리 수).

무엇이 아닌가
    학습 표본은 `train_ltr.py --split all` 의 리뷰 기반 9,900명 그대로다(2026-09-30). 로그가 쌓여도
    표본은 안 바뀌므로 **같은 데이터면 같은 모델**이 나온다 — 이 스크립트는 "재학습을 사람 손 없이
    안전하게 교체하는 길" 이지 온라인 학습이 아니다. 로그를 학습 표본으로 쓰는 것은 별도 설계
    (정답 정의·시점 피처·평가 틀)가 필요하다.

    HistGradientBoosting 은 partial_fit 이 없다. 전체 학습이 231,005행에 몇 분이라 증분이 필요 없다.

실행
    노트북:   python batch/jobs/retrain_ltr.py                       # serving/ 에 교체
    컨테이너: python batch/jobs/retrain_ltr.py --out-dir /data/ltr --reload-url http://127.0.0.1:8300/api/model/reload
              (deploy/ec2-1/retrain-ltr.sh · hwabun-ltr-retrain.timer 가 이 줄을 부른다)
    --dry-run 은 학습·평가만 하고 교체하지 않는다.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

if hasattr(sys.stdout, "reconfigure"):                  # Windows 콘솔 cp949 방어 (train_ltr 과 같게)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
SERVING = os.path.join(ROOT, "batch", "ingest", "data", "serving")
FILES = ("ltr_model.pkl", "ltr_model_meta.json")
RECALL_RE = re.compile(r"Recall@10\s+([0-9.]+)%")
TOLERANCE_PP = 0.5          # holdout_a 2,000명 잡음 폭 안 (부록 Q: 같은 조건 seed 차이 ≈ 0.3~0.6%p)


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def parse_recall(text):
    """eval_review_replay 출력에서 Recall@10 을 읽는다. 없으면 None (선형 폴백 경고도 여기서 걸린다)"""
    m = RECALL_RE.search(text or "")
    return float(m.group(1)) if m else None


def decide(current, candidate, tolerance=TOLERANCE_PP):
    """(교체 여부, 이유). 현행 수치가 없으면(모델 없음·평가 실패) 후보를 그대로 쓴다 —
    아무것도 없는 것보다 학습된 모델이 낫다. 후보 수치가 없으면 절대 교체하지 않는다."""
    if candidate is None:
        return False, "candidate_unmeasured"
    if current is None:
        return True, "no_current"
    if candidate + tolerance >= current:
        return True, "within_tolerance" if candidate < current else "not_worse"
    return False, f"worse_by_{current - candidate:.2f}pp"


def run(cmd, env_extra=None, cwd=ROOT):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", **(env_extra or {}))
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-2000:] + "\n" + r.stderr[-2000:] + "\n")
        raise SystemExit(f"실패: {' '.join(cmd)}")
    return r.stdout


def evaluate(model_dir, split, limit=None):
    """모델 폴더를 LTR_MODEL_DIR 로 넘겨 홀드아웃 Recall@10 을 읽는다. 폴더에 모델이 없으면 None"""
    if not all(os.path.exists(os.path.join(model_dir, f)) for f in FILES):
        return None
    cmd = [sys.executable, os.path.join(BD, "eval_review_replay.py"), "--split", split]
    if limit:
        cmd += ["--limit", str(limit)]
    out = run(cmd, {"LTR_MODEL_DIR": model_dir})
    if "ltr_model.pkl 이 없습니다" in out:
        return None
    return parse_recall(out)


def promote(src_dir, out_dir):
    """후보 파일 두 개를 out_dir 로 원자적으로 옮긴다"""
    os.makedirs(out_dir, exist_ok=True)
    for f in FILES:
        tmp = os.path.join(out_dir, f + ".new")
        shutil.copyfile(os.path.join(src_dir, f), tmp)
        os.replace(tmp, os.path.join(out_dir, f))


def reload_server(url, timeout=30):
    import urllib.request
    req = urllib.request.Request(url, data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.environ.get("LTR_MODEL_DIR") or SERVING,
                    help="교체할 모델 폴더. 컨테이너는 /data/ltr (볼륨), 노트북은 serving/")
    ap.add_argument("--split", default="holdout_a", choices=("holdout_a", "holdout_b", "holdout_c", "valid"),
                    help="고르는 집합. holdout_b 는 확인용이라 자동 교체 기준으로 쓰지 않는다")
    ap.add_argument("--tolerance", type=float, default=TOLERANCE_PP,
                    help="현행보다 이만큼(%%p)까지 낮아도 교체한다. 잡음 폭")
    ap.add_argument("--seed", type=int, default=1, help="train_ltr --seed (정본 1, Jira 322)")
    ap.add_argument("--limit", type=int, default=None, help="평가 인원 제한 (빠른 점검용)")
    ap.add_argument("--reload-url", default=None, help="교체 뒤 부를 POST /api/model/reload")
    ap.add_argument("--dry-run", action="store_true", help="학습·평가만 하고 교체하지 않는다")
    a = ap.parse_args()

    t0 = time.perf_counter()
    work = tempfile.mkdtemp(prefix="ltr_candidate_")
    log(f"후보 학습 → {work} (seed {a.seed})")
    out = run([sys.executable, os.path.join(BD, "train_ltr.py"), "--out", work,
               "--no-importance", "--seed", str(a.seed), "--split", "all"])   # 정본은 9,900명 전체 (2026-09-30)
    trees = re.search(r"트리 (\d+)개", out)
    log(f"학습 끝 — 트리 {trees.group(1) if trees else '?'}개")

    current_dir = a.out_dir if all(os.path.exists(os.path.join(a.out_dir, f)) for f in FILES) else SERVING
    log(f"현행 평가 ({a.split}) ← {current_dir}")
    cur = evaluate(current_dir, a.split, a.limit)
    log(f"후보 평가 ({a.split})")
    cand = evaluate(work, a.split, a.limit)
    ok, why = decide(cur, cand, a.tolerance)
    log(f"Recall@10 현행 {cur} → 후보 {cand} · 판정 {'교체' if ok else '유지'} ({why})")

    meta = json.load(open(os.path.join(work, "ltr_model_meta.json"), encoding="utf-8"))
    record = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "split": a.split, "limit": a.limit,
              "current_recall": cur, "candidate_recall": cand, "tolerance_pp": a.tolerance,
              "promoted": bool(ok and not a.dry_run), "reason": why, "dry_run": a.dry_run,
              "n_trees": meta.get("n_trees"), "trained_at": meta.get("trained_at"),
              "out_dir": os.path.abspath(a.out_dir), "reload": None,
              "elapsed_sec": round(time.perf_counter() - t0, 1)}
    if ok and not a.dry_run:
        promote(work, a.out_dir)
        log(f"교체 완료 → {a.out_dir}")
        if a.reload_url:
            try:
                record["reload"] = reload_server(a.reload_url)
                log(f"서버 리로드: {record['reload'].get('algorithm')}")
            except Exception as e:                      # 교체는 됐고 다음 재시작에 집힌다
                record["reload"] = {"error": str(e)}
                log(f"서버 리로드 실패 (다음 재시작 때 반영): {e}")
    shutil.rmtree(work, ignore_errors=True)

    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "retrain_log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
