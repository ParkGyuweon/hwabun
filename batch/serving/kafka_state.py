# -*- coding: utf-8 -*-
"""Kafka `activity-events` 를 구독해 사용자 세션 상태를 실시간으로 갱신한다 (Jira 226).

자리
    프론트 → 수집 서버(8080) → Kafka activity-events ─┬─ Spark (consumer group: 분석 정본 · Raw/Processed/Mart)
                                                      └─ 이 소비자 (group `recommend-state-v1`) → Engine.observe
    두 소비자는 서로 다른 consumer group 이라 같은 이벤트를 각자 전부 읽는다. Spark 정본을 우회하는 것이 아니라
    Spark 가 맡지 않는 시간 단위(초)를 맡는다. 실제 소비자의 "담으면 다음 화면이 바뀐다" 는 이 경로가 있어야 산다.

MVP 의 제한 (데이터 팀원 검토 2026-09-09 반영 — "단일 인스턴스 MVP 라는 제한 아래 안전")
    * API 프로세스 안의 전용 스레드. 스레드는 장애 경계가 아니다 — consumer 가 죽어도 API 는 살 수 있고 그 반대도.
      그래서 /health 에 alive · lag · 마지막 처리 시각을 그대로 드러낸다
    * 단일 replica. Kafka key 가 session_id 라 같은 persona 가 여러 파티션에 흩어진다 → 소비자를 여러 대 두면
      상태가 갈린다. 확장은 별도 `recommend-state-updater` + Redis (운영 단계)
    * `enable.auto.commit=false`. 상태 반영 + 세션 로그(JSONL) 기록이 끝난 뒤에 commit 한다.
      재기동은 committed offset 부터 이어 읽는다. `auto.offset.reset=latest` 는 group 에 offset 이 없는 첫 기동에만 적용
    * event_id 중복 제거. 계약상 같은 event_id 가 Kafka 에 여러 번 올 수 있고(Processed 단계에서 제거) 우리는 그 전 단계를
      읽으므로 직접 건다 (최근 20만 건 LRU)
    * 상태에 영향 없는 이벤트(노출·page_view 등)는 바로 버린다 — SessionLog 의 필터와 같은 기준

라이브러리는 confluent-kafka (librdkafka). kafka-python 은 이 레포의 `kafka/` 폴더와 모듈 이름이 충돌해
`import kafka` 가 폴더를 잡는다 — 쓰지 않는다.

떼고 붙이기
    KAFKA_BOOTSTRAP_SERVERS 가 없으면 이 모듈은 아예 시작하지 않고 서버는 지금과 같다 (POST /api/events 만).
    나중에 Spark 스트리밍 → Delta 경로로 바꾸면, 이 파일 대신 그 어댑터가 같은 `engine.observe` 를 부르면 된다.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict

TOPIC = os.environ.get("ACTIVITY_EVENTS_TOPIC", "activity-events")
GROUP = os.environ.get("RECOMMEND_STATE_GROUP", "recommend-state-v1")
SUPPORTED_SCHEMA_PREFIX = ("0.2.", "0.3.")          # 계약 schema_version — 앞자리만 본다 (draft 접미 허용)


class Dedupe:
    """event_id 최근 N건 LRU"""

    def __init__(self, size=200_000):
        self.size = size
        self._d: OrderedDict[str, None] = OrderedDict()

    def seen(self, key) -> bool:
        if key in self._d:
            self._d.move_to_end(key)
            return True
        self._d[key] = None
        if len(self._d) > self.size:
            self._d.popitem(last=False)
        return False


def parse(value: bytes | str) -> dict | None:
    """Kafka 메시지(수집 서버 KafkaEventMessage, snake_case JSON) → observe 에 넘길 이벤트. 못 쓰면 None"""
    try:
        m = json.loads(value if isinstance(value, str) else value.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(m, dict):
        return None
    sv = str(m.get("schema_version") or "")
    if not sv.startswith(SUPPORTED_SCHEMA_PREFIX):
        return None
    pid, name, eid = m.get("persona_id"), m.get("event_name"), m.get("event_id")
    if not pid or not name or not eid:
        return None
    props = m.get("properties")
    return {"event_id": eid, "persona_id": pid, "event_name": name,
            "product_id": m.get("product_id"), "properties": props if isinstance(props, dict) else {}}


class StateConsumer(threading.Thread):
    def __init__(self, engine, bootstrap, topic=TOPIC, group=GROUP, max_poll=500, poll_timeout=1.0,
                 consumer_factory=None, log=print, dedupe_size=200_000, observer=None):
        super().__init__(daemon=True, name="kafka-state")
        self.engine = engine
        self.observer = observer          # (persona_id, event_name) — 상태 필터·중복 제거 **전** 모든 메시지 (Jira 337 /pipeline)
        self.bootstrap, self.topic, self.group = bootstrap, topic, group
        self.max_poll, self.poll_timeout = int(max_poll), float(poll_timeout)
        self._broker_down = False
        self.consumer_factory = consumer_factory or self._default_factory
        self.log = log
        self.dedupe = Dedupe(dedupe_size)
        self.state_names = engine.session_log.state_names        # None 이면 전부
        self._stop = threading.Event()
        self.stats = {"alive": False, "connected": False, "batches": 0, "processed": 0, "filtered": 0,
                      "duplicates": 0, "invalid": 0, "commits": 0, "errors": 0, "broker_errors": 0, "lag": None,
                      "last_processed_at": None, "last_error": None, "topic": topic, "group": group,
                      "bootstrap": bootstrap}
        self._consumer = None

    # ── consumer ──────────────────────────────────────────────────────────
    def _on_broker_error(self, err):
        """librdkafka 는 브로커가 없어도 Consumer 객체를 만들어 준다 — 연결 실패는 이 콜백으로만 안다.
        그래서 connected 는 '메시지를 받았거나 파티션이 배정됐다' 로 켜고, 여기서 끈다"""
        self.stats["broker_errors"] = self.stats.get("broker_errors", 0) + 1
        self.stats["connected"] = False
        self._broker_down = True                # 메시지를 다시 받을 때까지 assignment 만으로 켜지 않는다
        self.stats["last_error"] = str(err)[:200]

    def _default_factory(self):
        from confluent_kafka import Consumer
        return Consumer({
            "bootstrap.servers": self.bootstrap,
            "group.id": self.group,
            "enable.auto.commit": False,          # 상태 반영 뒤에 우리가 commit
            "auto.offset.reset": "latest",        # group 에 offset 이 없는 첫 기동에만 적용
            "max.poll.interval.ms": 300000,
            "session.timeout.ms": 30000,
            "error_cb": self._on_broker_error,
            "log_level": 3,                       # librdkafka 의 자체 stderr 로그는 오류만
        })

    def stop(self, timeout=10.0):
        self._stop.set()
        self.join(timeout)

    # ── 처리 ──────────────────────────────────────────────────────────────
    def process_batch(self, values) -> int:
        """메시지 value 들 → persona 별로 묶어 observe. 처리한 이벤트 수를 돌려준다"""
        by_pid: dict[str, list] = {}
        part_of: dict[str, object] = {}
        for item in values:                                    # value 또는 (value, partition)
            v, part = (item if isinstance(item, tuple) else (item, None))
            ev = parse(v)
            if ev is None:
                self.stats["invalid"] += 1
                continue
            obs = getattr(self, "observer", None)          # __new__ 로 만든 테스트 객체도 견딘다
            if obs is not None:
                try:
                    obs(ev["persona_id"], ev["event_name"])
                except Exception:
                    pass                                       # 화면용 카운터가 상태 반영을 막으면 안 된다
            if self.state_names is not None and ev["event_name"] not in self.state_names:
                self.stats["filtered"] += 1
                continue
            if self.dedupe.seen(ev["event_id"]):
                self.stats["duplicates"] += 1
                continue
            by_pid.setdefault(ev["persona_id"], []).append(
                {"event_name": ev["event_name"], "product_id": ev["product_id"], "properties": ev["properties"]})
            part_of.setdefault(ev["persona_id"], part)          # key=session_id 라 한 사람은 한 파티션
        n = 0
        for pid, evs in by_pid.items():
            n += self.engine.observe(pid, evs, persist=False,   # 상태만 반영
                                     source="kafka", partition=part_of.get(pid))
        if by_pid:                                             # 세션 로그 JSONL 은 배치당 파일 한 번만 연다
            self.engine.session_log.append_many(by_pid.items())
        if n:
            self.stats["processed"] += n
            self.stats["last_processed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        return n

    def _lag(self, consumer):
        try:
            total = 0
            for tp in consumer.assignment():
                lo, hi = consumer.get_watermark_offsets(tp, cached=True)
                pos = consumer.position([tp])[0].offset
                if pos >= 0 and hi >= 0:
                    total += max(0, hi - pos)
            return total
        except Exception:
            return None

    def run(self):
        self.stats["alive"] = True
        backoff = 1.0
        while not self._stop.is_set():
            try:
                consumer = self.consumer_factory()
                consumer.subscribe([self.topic])
                self._consumer = consumer
                backoff = 1.0
                self.log(f"[kafka-state] {self.bootstrap} topic={self.topic} group={self.group} 구독 시작")
                while not self._stop.is_set():
                    msgs = consumer.consume(num_messages=self.max_poll, timeout=self.poll_timeout)
                    if not msgs:
                        try:
                            # 파티션이 배정돼 있으면 연결된 것 — 단, 브로커 오류 뒤에는 assignment 가
                            # 옛 값으로 남아 있으므로(실측: 브로커 죽은 28초 동안 connected=true) 켜지 않는다
                            if not self._broker_down and consumer.assignment():
                                self.stats["connected"] = True
                        except Exception:
                            pass
                        continue
                    self.stats["connected"] = True
                    if self._broker_down:                      # 복구 — 지난 오류는 지운다
                        self._broker_down = False
                        self.stats["last_error"] = None
                    values = []
                    for m in msgs:
                        err = m.error()
                        if err is not None:
                            if getattr(err, "code", lambda: None)() == getattr(err, "_PARTITION_EOF", -191):
                                continue
                            raise RuntimeError(str(err))
                        part = getattr(m, "partition", None)             # 파티션 번호는 /live 가 보인다 (Jira 295)
                        values.append((m.value(), part() if callable(part) else None))
                    self.process_batch(values)
                    consumer.commit(asynchronous=False)    # 상태 반영·기록 뒤에 commit
                    self.stats["commits"] += 1
                    self.stats["batches"] += 1
                    self.stats["lag"] = self._lag(consumer)
                try:
                    consumer.close()
                except Exception:
                    pass
            except Exception as ex:                        # 브로커 없음·네트워크·역직렬화 밖 오류 — 물러났다 다시
                self.stats["errors"] += 1
                self.stats["connected"] = False
                self.stats["last_error"] = f"{ex.__class__.__name__}: {ex}"[:200]
                self.log(f"[kafka-state] 오류 {self.stats['last_error']} — {backoff:.0f}초 뒤 재시도")
                if self._stop.wait(backoff):
                    break
                backoff = min(backoff * 2, 30.0)
        self.stats["alive"] = False
        self.stats["connected"] = False

    def health(self) -> dict:
        return dict(self.stats)
