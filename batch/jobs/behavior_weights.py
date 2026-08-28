"""
행동 가중치 로더 — frontend/src/types/log.ts 를 직접 읽는다.

가중치의 단일 소스는 `log.ts` 하나다. 값을 파이썬 쪽에 복사해두면
프론트가 고쳤을 때 조용히 어긋나므로, 원본을 파싱해서 쓴다.
파싱에 실패하면 예외로 죽인다 — 낡은 값으로 계속 도는 것보다 낫다.
"""
import os
import re

BD = os.path.dirname(os.path.abspath(__file__))
LOG_TS = os.path.normpath(os.path.join(
    BD, "..", "..", "frontend", "src", "types", "log.ts"))

_ENTRY = re.compile(r"^\s*'?([A-Za-z_][A-Za-z0-9_]*)'?\s*:\s*(-?\d+(?:\.\d+)?)\s*,", re.M)
_SET_ITEM = re.compile(r"'([A-Za-z_][A-Za-z0-9_]*)'")


def _block(src, header):
    """`header` 로 시작하는 선언의 중괄호 블록 본문을 잘라낸다"""
    i = src.index(header)
    s = src.index("{", i)
    depth, j = 0, s
    while True:
        if src[j] == "{": depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0: break
        j += 1
    return src[s + 1:j]


def _strip_comments(t):
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return re.sub(r"//[^\n]*", "", t)


def load(path=None):
    """{'event': {...}, 'section': {...}, 'negative': {...}, 'scroll': [(임계, 가중), ...]}"""
    path = path or LOG_TS
    src = open(path, encoding="utf-8").read()

    event = {k: float(v) for k, v in
             _ENTRY.findall(_strip_comments(_block(src, "EVENT_WEIGHT")))}
    section = {k: float(v) for k, v in
               _ENTRY.findall(_strip_comments(_block(src, "SECTION_DWELL_WEIGHT")))}

    intent = dict(re.findall(r"^\s*'?([a-z][a-z0-9_]*)'?\s*:\s*'([a-z]+)'\s*,",
                             _strip_comments(_block(src, "EVENT_INTENT")), re.M))

    i = src.index("NEGATIVE_EVENTS")
    negative = set(_SET_ITEM.findall(src[i:src.index("]", i)]))

    body = _strip_comments(_block(src, "export function scrollDepthWeight"))
    scroll = [(float(a), float(b)) for a, b in
              re.findall(r"depthPercent\s*>=\s*(\d+)\s*\)\s*return\s*(-?\d+(?:\.\d+)?)", body)]

    if not (event and section and negative and scroll and intent):
        raise RuntimeError(f"log.ts 파싱 실패 — 형식이 바뀐 것 같다: {path}")
    missing = set(event) - set(intent)
    if missing:
        raise RuntimeError(f"EVENT_INTENT 에 빠진 이벤트: {sorted(missing)}")
    return {"event": event, "section": section, "intent": intent,
            "negative": negative, "scroll": sorted(scroll, reverse=True)}


def scroll_weight(depth_percent, table):
    for lo, w in table:
        if depth_percent >= lo: return w
    return 0.0


if __name__ == "__main__":
    import sys
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    W = load()
    print(f"출처 {LOG_TS}")
    print(f"이벤트 가중치 {len(W['event'])}종 / 섹션 {len(W['section'])}종 "
          f"/ 감점 {len(W['negative'])}종 / intent {len(set(W['intent'].values()))}분류")
    print("감점 이벤트:", ", ".join(f"{k} {W['event'][k]:+.1f}" for k in sorted(W["negative"])))
    print("스크롤 깊이:", " · ".join(f"{int(a)}%→{b}" for a, b in W["scroll"]))
    top = sorted(W["event"].items(), key=lambda x: -x[1])[:5]
    print("가장 강한 신호:", " · ".join(f"{k} {v}" for k, v in top))
