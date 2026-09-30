"""고객 피드백 분류 서빙 (Jira 353).

백엔드가 ``feedback_classification`` 의 PENDING·FAILED 행을 집어서 이 엔드포인트를 부른다.
**이 모듈은 DB 를 건드리지 않는다.** 라벨만 돌려주고, 쓰기는 테이블 주인인 shop_backend 가 한다
(2026-09-18 백엔드 합의, 문서 ``피드백_분류_연결_요청_0918.md``).

분류 로직은 ``simulator/feedback/classify_feedback.py`` 의 ``Classifier`` 를 **그대로** 쓴다.
서빙용 사본을 만들면 어휘집 판이 올라갈 때 배치 CLI 와 서버가 조용히 갈린다.

계약 ``contracts/feedback-classification.md`` 0.2.0 의 핵심 두 가지를 여기서도 지킨다.

* **축은 고객이 고른 입력이다.** 분류기는 축을 추론하지 않고 그 축 안의 카테고리만 고른다
  (``axis_is_input``). 백엔드가 저장한 ``axis_id`` 를 그대로 받는다.
* **기타(other)는 단독으로만 붙는다.** 그 축에서 하나도 못 고르면 카테고리만 ``other`` 가 되고
  축은 고객이 고른 값 그대로 남는다.

금지어 대조에는 LLM 을 쓰지 않는다. 사전 대조라 분류가 실패해도 결과가 나온다.
"""
import os
import re
import sys

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
FEEDBACK_DIR = os.path.join(ROOT, "simulator", "feedback")
sys.path.insert(0, FEEDBACK_DIR)

from classify_feedback import Classifier, MODEL, load_vocab  # noqa: E402
from banned_terms import BannedTerms  # noqa: E402

# 처방과 별도 스위치다. 처방은 비용 때문에 시연 직전에만 켜지만, 분류는 매일 06:00 배치가
# 부르므로 기본이 on 이어야 한다. 키는 같은 GMS_KEY 를 쓴다.
ENABLED_DEFAULT = (os.environ.get("FEEDBACK_CLASSIFY_LLM", "on") or "on").strip().lower() \
    not in ("off", "0", "false", "no")

_vocab = _axes = _by_id = _banned = None


def load():
    """어휘집과 금지어를 한 번만 읽는다. 반환은 (vocab, axes, axis_id->label, BannedTerms)."""
    global _vocab, _axes, _by_id, _banned
    if _vocab is None:
        _vocab, _axes = load_vocab()
        # Classifier 는 축을 **표시 라벨**로 받는다. 백엔드가 주는 것은 axis_id 라 여기서 뒤집는다.
        _by_id = {ax["id"]: ax["label"] for ax in _vocab["axes"]}
        _banned = BannedTerms()
    return _vocab, _axes, _by_id, _banned


# ── 개인정보 가리기 ─────────────────────────────────────────────────────────
# 고객이 주관식 칸에 전화번호·메일·카드/계좌 번호를 적는 일이 있다. 외부 LLM 에는 가린 문장만 보낸다.
# **저장본(body)은 바꾸지 않는다** — 이 함수의 결과는 프롬프트에만 들어간다. 금지어 대조도 원문으로 한다.
# 순서가 중요하다: +82 전화 → 12자리 이상 숫자 → 국내 전화. 카드 번호 안의 "010-…" 조각을 전화로 먼저 잡지 않게.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_PHONE_INTL = re.compile(r"\+?82[\s.-]?\(?0?\)?1[016789][\s.-]?\d{3,4}[\s.-]?\d{4}(?!\d)")
_LONG_DIGITS = re.compile(r"(?<!\d)\d(?:[ -]?\d){11,}(?!\d)")
_PHONE_KR = re.compile(r"(?<!\d)(?:01[016789][\s.-]?\d{3,4}[\s.-]?\d{4}|0\d{1,2}-\d{3,4}-\d{4})(?!\d)")


def redact_pii(text: str) -> str:
    """전화번호 → [전화번호], 메일 → [이메일], 12자리 이상 숫자(카드·계좌) → [번호]."""
    if not text:
        return text
    t = _EMAIL.sub("[이메일]", text)
    t = _PHONE_INTL.sub("[전화번호]", t)
    t = _LONG_DIGITS.sub("[번호]", t)
    t = _PHONE_KR.sub("[전화번호]", t)
    return t


def axis_label(axis_id: str):
    """모르는 axis_id 면 None. 계약 밖 값을 LLM 에 넘기지 않는다."""
    _, _, by_id, _ = load()
    return by_id.get((axis_id or "").strip())


def make_classifier(client, model: str = MODEL, lang: str = "ko") -> Classifier:
    vocab, axes, _, _ = load()
    return Classifier(client, axes, vocab["other"], model=model, lang=lang)


def check_banned(body: str):
    """(걸린 금지어, 기본 숨김 여부). 사전 대조라 LLM 과 무관하게 항상 돈다."""
    _, _, _, banned = load()
    hits = banned.find(body or "")
    return hits, bool(hits)


def classify_one(clf: Classifier, item: dict, product_name: str = "") -> dict:
    """한 건. 예외를 밖으로 던지지 않는다 — 한 건이 죽어도 배치의 나머지는 살아야 한다."""
    vocab, _, _, _ = load()
    feedback_id = item.get("feedback_id")
    body = (item.get("body") or "").strip()
    label = axis_label(item.get("axis_id"))
    hits, hidden = check_banned(body)
    out = {
        "feedback_id": feedback_id,
        "banned_terms": hits,
        "hidden_by_default": hidden,
        "classifier": clf.model,
        "vocab_version": vocab["schema_version"],
    }
    if label is None:
        return {**out, "status": "FAILED", "labels": [], "primary_category_id": None,
                "off_axis_hint": None,
                "error": f"unknown axis_id: {item.get('axis_id')!r}"}
    if not body:
        return {**out, "status": "FAILED", "labels": [], "primary_category_id": None,
                "off_axis_hint": None, "error": "empty body"}
    try:
        got = clf.classify_in_axis(redact_pii(body), label, product=product_name)   # LLM 에는 가린 문장만
    except Exception as exc:                      # noqa: BLE001  한 건의 실패가 배치를 세우면 안 된다
        return {**out, "status": "FAILED", "labels": [], "primary_category_id": None,
                "off_axis_hint": None, "error": f"{type(exc).__name__}: {exc}"}
    return {
        **out,
        "status": "COMPLETED",
        "labels": [{"axis_id": l["axis_id"], "category_id": l["category_id"]}
                   for l in got["labels"]],
        "primary_category_id": got["category_id"],
        # 다른 축 얘기로 보인다는 힌트. 재분류는 하지 않는다 (계약 0.2.0)
        "off_axis_hint": (_by_id_of_label(got["off_axis_hint"]) if got.get("off_axis_hint") else None),
    }


def _by_id_of_label(label: str):
    """Classifier 는 축을 라벨로 돌려준다. 백엔드가 쓰는 것은 id 다."""
    vocab, _, _, _ = load()
    for ax in vocab["axes"]:
        if ax["label"] == label:
            return ax["id"]
    return None


def classify_items(items, client, model: str = MODEL, names=None) -> list:
    """여러 건. ``names`` 는 product_id -> 상품명(프롬프트 참고용, 없으면 빈 문자열)."""
    clf = make_classifier(client, model=model)
    names = names or {}
    return [classify_one(clf, it, names.get(it.get("product_id"), "")) for it in items]
