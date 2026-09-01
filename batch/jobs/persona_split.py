"""
페르소나 분할 — 파라미터를 고른 데이터로 성적을 내지 않기 위해.

    train 60%   후보 파라미터 탐색
    valid 20%   그중 하나를 선택 (스케줄 · λ · λ_mmr · 노출 정책)
    test  20%   선택이 끝난 뒤 **한 번만** 최종 성능 보고

후보를 여럿 재보고 제일 좋은 것을 고르면, 그 값에는 실력뿐 아니라 **그 표본에만
우연히 맞은 몫**이 섞인다. 실제로 하루에 스케줄 5안 · MMR λ 5개 · 후보 풀 4개 ·
브랜드 상한 4개를 같은 9,900명에서 고르고 같은 9,900명에서 보고했다. 그 수치는
"왜 그 값을 골랐나" 한 질문에 무너진다.

`persona_id` 해시 기반이라 **별도 파일 없이 재현**된다. 규칙은
docs/ai/recommendation-design.md 7-2 에서 확정한 것을 그대로 쓴다 —
분할 기준이 바뀌면 이전 수치와 비교할 수 없으므로 `split-v1` 을 고정한다.
"""
import hashlib

SPLIT_VERSION = "split-v1"
TRAIN, VALID, TEST = "train", "valid", "test"
SPLITS = (TRAIN, VALID, TEST)


def split_of(persona_id):
    """persona_id -> train | valid | test"""
    digest = hashlib.md5(f"{SPLIT_VERSION}|{persona_id}".encode()).hexdigest()
    bucket = int(digest[:8], 16) % 10
    return TRAIN if bucket < 6 else VALID if bucket < 8 else TEST


def select(personas, split):
    """split 이 'all' 이면 전원, 아니면 해당 집합만"""
    if split in (None, "all"):
        return list(personas)
    if split not in SPLITS:
        raise ValueError(f"알 수 없는 split: {split} (train|valid|test|all)")
    return [p for p in personas if split_of(p["persona_id"]) == split]


def counts(personas):
    out = {s: 0 for s in SPLITS}
    for p in personas:
        out[split_of(p["persona_id"])] += 1
    return out
