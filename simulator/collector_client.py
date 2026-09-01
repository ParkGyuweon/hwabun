# -*- coding: utf-8 -*-
"""
수집 API 전송 클라이언트 — 생성기와 에이전트 러너가 함께 쓴다.

**백프레셔를 존중한다.** 수집 서버는 포화 시 429(+Retry-After)를, Kafka 장애 시
503 을 내려준다. 재시도 없이 버리면 부하 테스트에서 "서버가 흘린 것" 과
"생성기가 버린 것" 이 구분되지 않는다. 정책은 프론트 로거(frontend/src/lib/logger.ts)와
같게 맞춘다 — 같은 서버에 같은 계약으로 보내는데 클라이언트마다 다르게 굴면
측정값을 해석할 수 없다.

    429            Retry-After 를 존중하고 기다린다
    502 503 504    게이트웨이·Kafka 장애. 지수 백오프로 재시도한다
    413            본문 과대. 배치를 반으로 쪼개 다시 보낸다 (같은 크기 재시도는 무의미)
    그 외 4xx      요청 자체가 잘못됐다. 재시도하지 않고 버리되 한 번만 알린다
    네트워크 오류   지나가는 문제로 보고 재시도한다

전송하지 못한 이벤트는 **세어서 돌려준다.** 조용히 사라지면 수집률이 부풀려진다.
"""
import json
import time
import urllib.error
import urllib.request

MAX_BATCH = 100          # 수집 서버 EventBatchRequest 의 @Size(max = 100)
MAX_RETRIES = 5
BACKOFF_BASE = 0.5       # 0.5 -> 1 -> 2 -> 4 -> 8 초
BACKOFF_CAP = 30.0
RETRYABLE = frozenset((429, 502, 503, 504))


class CollectorClient:
    """한 번의 실행 동안 상태(배치 크기·통계)를 들고 있는다"""

    def __init__(self, base_url, timeout=40, max_retries=MAX_RETRIES,
                 max_batch=MAX_BATCH, rps=0, log=print):
        self.url = base_url.rstrip("/") + "/api/events"
        self.timeout = timeout
        self.max_retries = max_retries
        # 413 을 받으면 줄이고, 성공이 이어지면 조금씩 되돌린다
        self.batch_size = max_batch
        self.max_batch = max_batch
        self.rps = rps
        self.log = log
        self.stats = {"sent": 0, "dropped": 0, "gave_up": 0,
                      "retries": 0, "waited_sec": 0.0}
        self._warned = set()
        self._t0 = time.time()
        self._cursor = 0

    # ── 공개 API ─────────────────────────────────────────────────────────
    def send(self, events, schema_version="0.2.0-draft", headers=None):
        """이벤트 목록을 배치로 나눠 보낸다. 통계를 갱신하고 돌려준다"""
        i = 0
        while i < len(events):
            chunk = events[i:i + self.batch_size]
            ok = self._send_chunk(chunk, schema_version, headers or {})
            if ok is False and self.batch_size < len(chunk):
                continue                      # 413 으로 줄었다. 같은 자리를 다시 자른다
            i += len(chunk)
            self._throttle(i)
        return self.stats

    # ── 내부 ─────────────────────────────────────────────────────────────
    def _send_chunk(self, chunk, schema_version, headers):
        body = json.dumps({"schema_version": schema_version, "events": chunk},
                          ensure_ascii=False).encode()
        for attempt in range(self.max_retries + 1):
            status, retry_after = self._post(body, headers)

            if status == "ok":
                self.stats["sent"] += len(chunk)
                if self.batch_size < self.max_batch:
                    self.batch_size = min(self.max_batch, self.batch_size + 10)
                return True

            if status == 413:
                self.batch_size = max(1, self.batch_size // 2)
                self._warn(413, f"본문 과대 — 배치를 {self.batch_size}건으로 줄임")
                return False

            if status in RETRYABLE or status == "network":
                if attempt == self.max_retries:
                    break
                wait = retry_after if retry_after else min(
                    BACKOFF_CAP, BACKOFF_BASE * (2 ** attempt))
                self.stats["retries"] += 1
                self.stats["waited_sec"] += wait
                time.sleep(wait)
                continue

            # 400/403/404/422 — 몇 번을 보내도 같은 이유로 거절당한다
            self._warn(status, f"재시도하지 않고 {len(chunk)}건을 버림")
            self.stats["dropped"] += len(chunk)
            return True

        self.stats["gave_up"] += len(chunk)
        self._warn("gave_up", f"{self.max_retries}회 재시도 후 {len(chunk)}건 포기")
        return True

    def _post(self, body, headers):
        req = urllib.request.Request(
            self.url, data=body, method="POST",
            headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return ("ok" if r.status in (200, 202) else r.status), None
        except urllib.error.HTTPError as e:
            after = e.headers.get("Retry-After") if e.headers else None
            try:
                after = float(after) if after else None
            except ValueError:
                after = None                  # HTTP-date 형식은 무시하고 백오프로 간다
            if e.code not in RETRYABLE and e.code != 413:
                detail = e.read()[:200].decode("utf-8", "replace")
                self._warn(e.code, f"HTTP {e.code} — {detail}")
            return e.code, after
        except Exception as exc:
            self._warn("network", f"전송 실패 — {exc}")
            return "network", None

    def _throttle(self, sent_so_far):
        """--rps 로 초당 이벤트 수를 제한한다. 부하 강도를 단계로 올릴 때 쓴다"""
        if not self.rps:
            return
        gap = sent_so_far / self.rps - (time.time() - self._t0)
        if gap > 0:
            time.sleep(gap)

    def _warn(self, key, message):
        """같은 원인은 한 번만 알린다. 매번 찍으면 진짜 원인이 묻힌다"""
        if key in self._warned:
            return
        self._warned.add(key)
        self.log(f"  [수집 API] {message}")

    def summary(self):
        s = self.stats
        line = (f"전송 {s['sent']:,}건 · 버림 {s['dropped']:,}건 · "
                f"포기 {s['gave_up']:,}건 · 재시도 {s['retries']}회")
        if s["waited_sec"]:
            line += f" (백프레셔 대기 {s['waited_sec']:.1f}초)"
        return line
