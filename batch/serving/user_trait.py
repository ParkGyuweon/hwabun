"""장기 성향(`user_trait_daily`) 조회 — 추천 응답 `long_term_trait` (Jira 306, 프론트 요청서 §2-A).

프론트 `lib/trait.ts` 는 세션 성향 5종(price·ingredient·review·concern·participate)을 브라우저에서 누적하고,
마트 점수를 `long_term_blend_weight` 로 섞도록 만들어져 있는데 읽을 경로가 없었다. 추천 응답 최상위에
한 칸을 실어 준다. 요청당 조회는 없다 — 시작 때 표를 메모리에 올리고 `reload_sec` 마다 다시 읽는다.

조회 인터페이스가 정본이고 저장 형식은 아니다 (데이터 파트 회신 2026-09-15). 로더는 순서대로 시도한다.
  1. dw MySQL projection  — `DW_MYSQL_HOST` 가 있을 때. 계약 dw-schema.md §1 의 정본 경로 (A).
  2. 스냅샷 파일         — `USER_TRAIT_SNAPSHOT_PATH`, 없으면 `/data/user_trait_snapshot.jsonl`,
                            없으면 레포 `batch/ingest/data/serving/user_trait_snapshot.jsonl` (B, 폴백).
  3. 없음                — 응답은 `null`. 서버는 그대로 돈다.

행 스키마 (두 경로 모두 같다 — 사용자당 trait 5행):
  user_id · identity_scope(account|persona) · trait · trait_score · is_primary_trait · window_end_date · trait_policy_version
`actor_type='user'` 로 이미 좁혀진 행만 온다고 가정한다 (합성 페르소나 행은 identity_scope=persona 로 구분).

신선도 (Jira 319, 데이터 파트 합의 2026-09-16 — 마트 배치는 하루 1회):
  * 관측  — `health()` 에 `window_end_date`(표 최댓값)·`age_days`(오늘 KST − 그 날짜)·`stale`
             (`USER_TRAIT_STALE_DAYS`=2 초과). 배치가 안 돌았다는 것을 가장 먼저 아는 자리가 소비자라서 여기 둔다.
  * 소비자 판단 — 응답 `window_end_date` 는 그대로 싣는다. 가중치를 낮출지는 프론트 몫.
  * TTL   — `age_days` 가 `USER_TRAIT_MAX_AGE_DAYS`(=14) 를 넘으면 `get()` 은 None. 값을 믿으면 안 되는 선이고,
             폴백은 프론트의 세션 성향. 0 이면 끈다.
"""
from __future__ import annotations

import csv
import json
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))

TRAITS = ("price", "ingredient", "review", "concern", "participate")
FIELDS = ("user_id", "identity_scope", "trait", "trait_score", "is_primary_trait",
          "window_end_date", "trait_policy_version")
# 회원 요청(persona_id = account_id)과 시뮬레이터 요청(persona_id = PC…)이 같은 쿼리 파라미터로 오므로
# 두 scope 를 순서대로 찾는다. 실회원 id 와 페르소나 id 는 형식이 달라 겹치지 않는다.
SCOPE_ORDER = ("account", "persona")
DEFAULT_SNAPSHOTS = ("/data/user_trait_snapshot.jsonl",
                     os.path.join(ROOT, "batch", "ingest", "data", "serving", "user_trait_snapshot.jsonl"))
RELOAD_SEC = int(os.environ.get("USER_TRAIT_RELOAD_SEC", "300") or 300)
# 신선도 경계 (Jira 319). 배치 주기(1일)의 2배가 경보선, 관측 창의 일부(14일)가 TTL. 0 은 끔
STALE_DAYS = int(os.environ.get("USER_TRAIT_STALE_DAYS", "2") or 0)
MAX_AGE_DAYS = int(os.environ.get("USER_TRAIT_MAX_AGE_DAYS", "14") or 0)
KST = timezone(timedelta(hours=9))


def today_kst() -> date:
    return datetime.now(KST).date()


def age_days(window_end_date, today=None) -> int | None:
    """오늘(KST) − window_end_date. 날짜가 없거나 형식이 아니면 None."""
    if not window_end_date:
        return None
    try:
        wed = date.fromisoformat(str(window_end_date)[:10])
    except ValueError:
        return None
    return ((today or today_kst()) - wed).days

# dw MySQL — 열 이름은 계약 dw-schema.md §4 그대로. 표가 다르게 만들어지면 DW_MYSQL_QUERY 로 SQL 을 통째로 바꾼다.
DEFAULT_QUERY = (
    "SELECT user_id, identity_scope, trait, trait_score, is_primary_trait, window_end_date, trait_policy_version "
    "FROM {table} WHERE trait_date_kst = (SELECT MAX(trait_date_kst) FROM {table}) AND actor_type = 'user'"
)


def _truthy(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "t", "y", "yes")
    return bool(v)


def aggregate(rows) -> dict:
    """(scope, user_id) → 응답 한 덩어리. 5행을 trait 별 점수로 접고 primary 는 is_primary_trait, 없으면 최고점."""
    out = {}
    for r in rows:
        uid, scope, trait = str(r["user_id"]), str(r.get("identity_scope") or "account"), str(r["trait"])
        if trait not in TRAITS:
            continue
        key = (scope, uid)
        d = out.setdefault(key, {t: 0.0 for t in TRAITS})
        d[trait] = round(float(r.get("trait_score") or 0.0), 4)
        if _truthy(r.get("is_primary_trait")):
            d["primary"] = trait
        wed = r.get("window_end_date")
        if wed is not None:
            wed = str(wed)[:10]
            d["window_end_date"] = max(d.get("window_end_date") or "", wed)
        if r.get("trait_policy_version"):
            d["trait_policy_version"] = str(r["trait_policy_version"])
    for (scope, uid), d in out.items():
        d.setdefault("primary", max(TRAITS, key=lambda t: d[t]))
        d.setdefault("window_end_date", None)
        d.setdefault("trait_policy_version", None)
        d["identity_scope"] = scope
    return out


def read_snapshot(path: str) -> list[dict]:
    """jsonl(한 줄 = 한 행) 또는 csv. 열은 FIELDS."""
    rows = []
    if path.endswith(".csv"):
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                rows.append(r)
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_mysql(cfg: dict) -> list[dict]:
    """dw MySQL projection. pymysql 이 없거나 접속이 안 되면 예외 — 호출자가 폴백한다."""
    import pymysql  # noqa: WPS433 — 선택 의존성. 서버 requirements 에는 넣어 둔다
    table = cfg.get("table") or "user_trait_daily"
    sql = cfg.get("query") or DEFAULT_QUERY.format(table=table)
    conn = pymysql.connect(host=cfg["host"], port=int(cfg.get("port") or 3306), user=cfg.get("user"),
                           password=cfg.get("password"), database=cfg.get("db") or "dw",
                           charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
                           connect_timeout=int(cfg.get("timeout") or 5), read_timeout=30)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return list(cur.fetchall())
    finally:
        conn.close()


def mysql_config_from_env(env=os.environ) -> dict | None:
    host = env.get("DW_MYSQL_HOST")
    if not host:
        return None
    return {"host": host, "port": env.get("DW_MYSQL_PORT", "3306"), "user": env.get("DW_MYSQL_USER"),
            "password": env.get("DW_MYSQL_PASSWORD"), "db": env.get("DW_MYSQL_DB", "dw"),
            "table": env.get("DW_MYSQL_TABLE", "user_trait_daily"), "query": env.get("DW_MYSQL_QUERY"),
            "timeout": env.get("DW_MYSQL_TIMEOUT_SEC", "5")}


class UserTraitStore:
    """`get(user_id)` 하나가 인터페이스다. 어디서 읽었는지는 `health()` 로만 드러난다."""

    def __init__(self, snapshot_paths=None, mysql=None, reload_sec=RELOAD_SEC, log=None,
                 stale_days=STALE_DAYS, max_age_days=MAX_AGE_DAYS, today=None):
        env_path = os.environ.get("USER_TRAIT_SNAPSHOT_PATH")
        self.snapshot_paths = tuple(snapshot_paths) if snapshot_paths is not None \
            else ((env_path,) if env_path else DEFAULT_SNAPSHOTS)
        self.mysql = mysql if mysql is not None else mysql_config_from_env()
        self.reload_sec = reload_sec
        self.log = log or (lambda m: print(m, flush=True))
        self._lock = threading.Lock()
        self.table: dict = {}
        self.source = None
        self.loaded_at = None
        self.error = None
        self.n_rows = 0
        self.window_end_date = None            # 표 전체의 최댓값 — 마트가 마지막으로 본 날
        self.stale_days, self.max_age_days = stale_days, max_age_days
        self._today = today or today_kst       # 테스트에서 날짜를 고정할 수 있게

    # ── 적재 ─────────────────────────────────────────────────────────────
    def load(self) -> str | None:
        rows, source, err = None, None, None
        if self.mysql:
            try:
                rows, source = read_mysql(self.mysql), f"dw_mysql:{self.mysql['host']}/{self.mysql.get('db') or 'dw'}"
            except Exception as ex:                       # 접속 실패·드라이버 없음 → 스냅샷으로
                err = f"dw_mysql: {ex.__class__.__name__}: {ex}"
                self.log(f"[user-trait] dw MySQL 읽기 실패, 스냅샷으로 폴백 — {err}")
        if rows is None:
            for p in self.snapshot_paths:
                if p and os.path.exists(p):
                    try:
                        rows, source = read_snapshot(p), f"snapshot:{p}"
                        break
                    except Exception as ex:
                        err = f"snapshot {p}: {ex.__class__.__name__}: {ex}"
                        self.log(f"[user-trait] 스냅샷 읽기 실패 — {err}")
        with self._lock:
            if rows is not None:
                self.table = aggregate(rows)
                self.n_rows = len(rows)
                self.source = source
                self.window_end_date = max((d["window_end_date"] for d in self.table.values()
                                            if d.get("window_end_date")), default=None)
            else:
                self.table, self.n_rows, self.source, self.window_end_date = {}, 0, None, None
            self.loaded_at = time.time()
            self.error = err
        if rows is not None:
            age = self.age_days()
            note = (f", window_end_date {self.window_end_date} ({age}일 전"
                    + (", TTL 초과 → 응답 null" if self.expired() else ", stale" if self.stale() else "") + ")"
                    if age is not None else "")
            self.log(f"[user-trait] {source} 에서 {self.n_rows}행 → 사용자 {len(self.table)}명{note}")
        return self.source

    # ── 신선도 (Jira 319) ─────────────────────────────────────────────────
    def age_days(self) -> int | None:
        return age_days(self.window_end_date, self._today())

    def stale(self) -> bool | None:
        """경보선. 날짜를 모르면 None."""
        a = self.age_days()
        return None if a is None else (self.stale_days > 0 and a > self.stale_days)

    def expired(self) -> bool:
        """TTL. 넘으면 get() 은 None. max_age_days 0 이면 절대 만료 안 함."""
        a = self.age_days()
        return a is not None and self.max_age_days > 0 and a > self.max_age_days

    def maybe_reload(self):
        if self.loaded_at is None or (self.reload_sec > 0 and time.time() - self.loaded_at >= self.reload_sec):
            self.load()

    # ── 조회 ─────────────────────────────────────────────────────────────
    def get(self, user_id, scopes=SCOPE_ORDER) -> dict | None:
        """응답 `long_term_trait`. 행이 없으면 None."""
        if not user_id:
            return None
        self.maybe_reload()
        if self.expired():
            return None
        uid = str(user_id)
        with self._lock:
            for s in scopes:
                d = self.table.get((s, uid))
                if d is not None:
                    return dict(d)
        return None

    def health(self) -> dict:
        return {"source": self.source, "rows": self.n_rows, "users": len(self.table),
                "loaded_at": (time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.loaded_at))
                              if self.loaded_at else None),
                "reload_sec": self.reload_sec, "error": self.error,
                # 신선도 (Jira 319) — Grafana 경보는 stale, 응답 null 전환은 expired
                "window_end_date": self.window_end_date, "age_days": self.age_days(),
                "stale": self.stale(), "stale_days": self.stale_days,
                "expired": self.expired(), "max_age_days": self.max_age_days}
