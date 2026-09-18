# -*- coding: utf-8 -*-
"""
시연 파이프라인 화면 (Jira 337, 2026-09-16) — `GET /pipeline` · `GET /pipeline/stats`
================================================================================

무엇을 보여주는가
    "1만 명이 사이트에서 움직인 로그가 Kafka 로 흩어져 들어가고, Spark 가 받아 정제하고, dw 마트가 되어 대시보드에
    뜬다" 를 **한 화면에서 왼쪽 → 오른쪽으로** 보인다. 리허설(09-17)에서 로그가 어디까지 흘렀는지 바로 짚기 위한 것.

        [사이트 활동]  →  [Kafka 3 파티션]  →  [Spark raw sink]  →  [dw 마트 22개]  →  [대시보드]
        페르소나/에이전트/  브로커 끝 오프셋·   워커·실행 앱          행 수·마지막 갱신    링크
        실사용자 분리        소비 위치·지연       (REST, 포트 개방 뒤)  (reader 계정 뒤)

`/live` 는 그대로 둔다 — 그건 "추천 상태에 반영됐다" 는 마지막 층 하나를 깊게 보는 화면이고, 이건 층 다섯을 얕게 이어 본다.

읽기만 한다
    다른 파트 자원(Kafka 브로커·Spark UI·dw MySQL)은 전부 조회만. 쓰는 것은 없다.
    각 감시자는 연결이 안 되면 그 칸을 "대기" 로 표시하고 나머지는 계속 돈다 — 한 칸이 죽어도 화면은 산다.

칸별 출처
    활동   : Kafka 소비자가 받은 **모든** 메시지(상태 필터 전). persona_id 접두로 PC=페르소나(생성기)·PA=에이전트·그 외=실사용자
    Kafka  : 같은 group.id 의 두 번째 Consumer(구독 안 함) 로 파티션별 끝 오프셋(브로커 생산량)과 committed(우리 소비 위치)
    Spark  : `SPARK_MASTER_UI` (예 http://<EC2-2>:18080) 의 `/json` — 살아 있는 워커·실행 중 앱. 09-16 현재 EC2-2 가
             127.0.0.1 에만 열어 두어 EC2-1 에서는 닫힘 → 민우님께 EC2-1 사설 IP 개방 요청
    dw     : `DW_MYSQL_*` (user_trait 와 같은 값) 로 information_schema + 마트 22개 COUNT(*)
    대시보드: `DASHBOARD_URL` 링크. 백엔드 API 6개가 생기면 숫자를 붙인다
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from collections import Counter, deque

# EC2-2 projection 기본 allowlist (streaming/jobs/dw_projection_source.py) 와 같은 22개.
# EC2-1 은 EC2-2 의 .env 를 공유하지 않으므로 여기에도 기본값을 둔다.
_MARTS_ENV = (os.environ.get("DW_PROJECTION_MARTS") or
              "user_trait_daily,brand_daily_kpi,product_daily_kpi,funnel_daily_kpi,"
              "brand_repurchase_daily,product_repurchase_daily,purchase_reason_daily,"
              "persona_segment_daily_kpi,brand_price_band_daily_kpi,segment_price_band_daily_kpi,"
              "brand_cohort_dim,commons_cohort_weekly,ingredient_weekly_interest,product_exit_daily,"
              "segment_content_daily,friction_daily,exit_daily,entry_source_daily,content_daily_kpi,"
              "content_conversion_daily,behavior_conversion_daily,event_daily")
# 쉼표 뒤 공백으로 적어도 되게 한다 — 안 벗기면 " brand_daily_kpi" 로 조회해 0행으로 보인다
MARTS = tuple(m for m in (x.strip() for x in _MARTS_ENV.split(",")) if m)
CONVERSION_EVENTS = ("add_to_cart", "begin_checkout", "purchase")


def classify(persona_id) -> str:
    """persona_id 접두 → 활동 주체. 생성기 PC· 에이전트 PA · 나머지(회원 uuid·익명)는 실사용자"""
    p = str(persona_id or "")
    if p.startswith("PC"):
        return "persona"
    if p.startswith("PA"):
        return "agent"
    return "real"


class ActorStats:
    """Kafka 로 들어온 모든 메시지를 주체별로 센다 (상태 필터 전이라 dwell 류도 포함 — '사이트에서 얼마나 움직였나')"""

    def __init__(self, window=120):
        self.lock = threading.Lock()
        self.window = window
        self._ticks = deque()                       # (ts, actor)
        self.total = Counter()                      # actor -> 메시지 수
        self.users = {"persona": set(), "agent": set(), "real": set()}
        self.conversions = {a: Counter() for a in ("persona", "agent", "real")}
        self.names = Counter()

    def record(self, persona_id, event_name):
        a = classify(persona_id)
        now = time.time()
        with self.lock:
            self._ticks.append((now, a))
            self.total[a] += 1
            self.users[a].add(persona_id)
            self.names[event_name] += 1
            if event_name in CONVERSION_EVENTS:
                self.conversions[a][event_name] += 1
            lim = now - self.window
            while self._ticks and self._ticks[0][0] < lim:
                self._ticks.popleft()

    def snapshot(self, seconds=60):
        now = time.time()
        with self.lock:
            per10 = Counter()
            series = [0] * seconds
            for ts, a in self._ticks:
                age = now - ts
                if age < 10:
                    per10[a] += 1
                idx = seconds - 1 - int(age)
                if 0 <= idx < seconds:
                    series[idx] += 1
            out = {}
            for a in ("persona", "agent", "real"):
                out[a] = {"total": self.total[a], "users": len(self.users[a]),
                          "per_sec_10s_avg": round(per10[a] / 10.0, 1),
                          **{k: self.conversions[a][k] for k in CONVERSION_EVENTS}}
            return {"actors": out, "series_60s": series, "total": sum(self.total.values()),
                    "users": sum(len(s) for s in self.users.values()),
                    "by_name": dict(self.names.most_common(6))}


class _Watcher(threading.Thread):
    """주기 폴러 공통: 예외는 상태에 남기고 다음 주기에 다시"""

    def __init__(self, name, interval):
        super().__init__(daemon=True, name=name)
        self.interval = interval
        self.lock = threading.Lock()
        self.state = {"configured": False, "reachable": False, "error": None, "at": None}
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def poll(self) -> dict:                          # 서브클래스: 성공 시 채울 dict 를 돌려준다
        raise NotImplementedError

    def run(self):
        while not self._stop.is_set():
            try:
                got = self.poll()
                with self.lock:
                    self.state.update(got); self.state.update(reachable=True, error=None,
                                                             at=time.strftime("%Y-%m-%dT%H:%M:%S"))
            except Exception as ex:
                with self.lock:
                    self.state.update(reachable=False, error=f"{ex.__class__.__name__}: {ex}"[:200],
                                      at=time.strftime("%Y-%m-%dT%H:%M:%S"))
            if self._stop.wait(self.interval):
                break

    def snapshot(self):
        with self.lock:
            return dict(self.state)


class BrokerWatch(_Watcher):
    """브로커 관점의 Kafka: 파티션별 끝 오프셋(생산 누적)·우리 group 의 committed(소비 위치)·지연·초당 생산량"""

    def __init__(self, bootstrap, topic, group, interval=2.0, consumer_factory=None):
        super().__init__("pipeline-broker", interval)
        self.bootstrap, self.topic, self.group = bootstrap, topic, group
        self.state.update(configured=bool(bootstrap), topic=topic, group=group, partitions={}, end_total=0,
                          committed_total=0, lag_total=0, produced_per_sec=0.0)
        self._consumer = None
        self._factory = consumer_factory
        self._last = None                            # (ts, end_total) 초당 생산량 계산용

    def _consumer_or_new(self):
        if self._consumer is None:
            if self._factory:
                self._consumer = self._factory()
            else:
                from confluent_kafka import Consumer
                # 구독하지 않는 Consumer: 같은 group.id 로 committed 만 묻는다. 구독이 없으니 리밸런스에 끼지 않는다
                self._consumer = Consumer({"bootstrap.servers": self.bootstrap, "group.id": self.group,
                                           "enable.auto.commit": False, "log_level": 3})
        return self._consumer

    def poll(self):
        if not self.bootstrap:
            raise RuntimeError("KAFKA_BOOTSTRAP_SERVERS 없음")
        from confluent_kafka import TopicPartition
        c = self._consumer_or_new()
        try:
            md = c.list_topics(self.topic, timeout=5)
            parts = sorted(md.topics[self.topic].partitions.keys())
            tps = [TopicPartition(self.topic, p) for p in parts]
            committed = {tp.partition: tp.offset for tp in c.committed(tps, timeout=5)}
            out, end_total, com_total, lag_total = {}, 0, 0, 0
            for p in parts:
                lo, hi = c.get_watermark_offsets(TopicPartition(self.topic, p), timeout=5)
                com = committed.get(p, -1001)
                com = max(0, com) if com >= 0 else None       # -1001 = 아직 commit 없음
                lag = (hi - com) if com is not None else None
                out[str(p)] = {"begin": lo, "end": hi, "committed": com, "lag": lag}
                end_total += hi; com_total += (com or 0); lag_total += (lag or 0)
        except Exception:
            try:
                c.close()
            except Exception:
                pass
            self._consumer = None
            raise
        now = time.time()
        pps = 0.0
        if self._last and now > self._last[0]:
            pps = max(0.0, (end_total - self._last[1]) / (now - self._last[0]))
        self._last = (now, end_total)
        return {"partitions": out, "end_total": end_total, "committed_total": com_total,
                "lag_total": lag_total, "produced_per_sec": round(pps, 1)}


class SparkWatch(_Watcher):
    """Spark 스탠드얼론 마스터 UI 의 /json — 워커·실행 앱. 포트가 닫혀 있으면 reachable=false 로 '대기'"""

    def __init__(self, base_url, interval=5.0, fetch=None):
        super().__init__("pipeline-spark", interval)
        self.base = (base_url or "").rstrip("/")
        self.state.update(configured=bool(self.base), url=self.base, workers_alive=0, cores=0, cores_used=0,
                          apps=[], completed=0, status=None)
        self._fetch = fetch or self._http

    @staticmethod
    def _http(url):
        with urllib.request.urlopen(url, timeout=4) as r:
            return json.loads(r.read().decode("utf-8"))

    def poll(self):
        if not self.base:
            raise RuntimeError("SPARK_MASTER_UI 없음")
        j = self._fetch(self.base + "/json")
        apps = [{"name": a.get("name"), "state": a.get("state"), "cores": a.get("cores"),
                 "duration_sec": round((a.get("duration") or 0) / 1000)} for a in (j.get("activeapps") or [])]
        return {"workers_alive": j.get("aliveworkers", 0), "cores": j.get("cores", 0),
                "cores_used": j.get("coresused", 0), "apps": apps,
                "completed": len(j.get("completedapps") or []), "status": j.get("status")}


class DwWatch(_Watcher):
    """dw MySQL — 스키마 존재·테이블 수·마트 행 수·마지막 갱신. user_trait 와 같은 DW_MYSQL_* 를 쓴다"""

    def __init__(self, cfg, marts=MARTS, interval=30.0, query=None):
        super().__init__("pipeline-dw", interval)
        self.cfg = cfg or {}
        self.marts = tuple(marts)
        self.state.update(configured=bool(self.cfg.get("host") and self.cfg.get("user")),
                          host=self.cfg.get("host"), db=self.cfg.get("db") or "dw",
                          schema_exists=False, tables=0, marts={m: None for m in self.marts})
        self._query = query or self._mysql

    def _mysql(self, sqls):
        import pymysql
        conn = pymysql.connect(host=self.cfg["host"], port=int(self.cfg.get("port") or 3306), user=self.cfg.get("user"),
                               password=self.cfg.get("password") or "", charset="utf8mb4",
                               connect_timeout=int(float(self.cfg.get("timeout") or 5)), read_timeout=10)
        try:
            out = []
            with conn.cursor() as cur:
                for s, args in sqls:
                    cur.execute(s, args); out.append(cur.fetchall())
            return out
        finally:
            conn.close()

    def poll(self):
        if not self.state["configured"]:
            raise RuntimeError("DW_MYSQL_HOST/USER 없음")
        db = self.state["db"]
        rows = self._query([("SELECT TABLE_NAME, TABLE_ROWS, UPDATE_TIME FROM information_schema.TABLES "
                             "WHERE TABLE_SCHEMA=%s", (db,))])[0]
        tables = {r[0]: r for r in rows}
        marts = {}
        present = [m for m in self.marts if m in tables]
        counts = self._query([(f"SELECT COUNT(*) FROM `{db}`.`{m}`", ()) for m in present]) if present else []
        for m in self.marts:
            if m not in tables:
                marts[m] = None
                continue
            n = counts[present.index(m)][0][0]
            upd = tables[m][2]
            marts[m] = {"rows": int(n), "updated": (upd.strftime("%Y-%m-%dT%H:%M:%S") if hasattr(upd, "strftime") else upd)}
        return {"schema_exists": bool(tables), "tables": len(tables), "marts": marts}


PIPELINE_HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>HWABUN — 데이터 파이프라인 현황</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>
:root{--bg:#FAF7F1;--card:#FFFFFF;--line:#E9ECEF;--fg:#2B2B2B;--mute:#6B7280;--acc:#A8C96E;--acc-light:#D8E9C3;--acc-deep:#7FA34A;--pink:#E68FA1;--brown:#7A5B43;--amber:#E3B04B}
*{box-sizing:border-box}body{margin:0 auto;background:var(--bg);color:var(--fg);font:13px/1.4 'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif;padding:10px 16px;max-width:1880px}
h1{font-size:18px;margin:0 0 2px;font-weight:700;color:var(--brown)}.sub{color:var(--mute);font-size:14px}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap}
.ctl{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.ctl label{color:var(--mute);font-size:13px}.ctl select,.ctl input{font:inherit;padding:4px 8px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--fg)}.ctl input{width:210px}
.btn{font:inherit;font-weight:700;font-size:13px;padding:6px 14px;border:0;border-radius:999px;background:var(--acc);color:#fff;cursor:pointer;box-shadow:0 2px 6px rgba(168,201,110,.35)}.btn:hover{background:var(--acc-deep)}.btn.stop{background:var(--pink)}.btn.alt{background:var(--brown)}.btn:disabled{opacity:.5;cursor:default}
.flow{display:grid;grid-template-columns:repeat(5,1fr);gap:0;align-items:stretch;margin-top:8px}
.stage{position:relative;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-right:28px;display:flex;flex-direction:column;gap:4px}
.stage:last-child{margin-right:0}.stage:not(:last-child)::after{content:'';position:absolute;right:-25px;top:50%;width:26px;height:26px;margin-top:-13px;background:linear-gradient(90deg,var(--acc-light),var(--acc));clip-path:polygon(0 30%,55% 30%,55% 0,100% 50%,55% 100%,55% 70%,0 70%);opacity:.9}
.stage.wait{border-style:dashed}.stage h2{font-size:14px;margin:0;display:flex;align-items:center;gap:8px;color:var(--brown)}
.dot{width:10px;height:10px;border-radius:50%;background:#C9CDD2;display:inline-block}.dot.ok{background:var(--acc-deep)}.dot.warn{background:var(--amber)}.dot.off{background:var(--pink)}
.k{color:var(--mute);font-size:12px}.v{font-size:26px;line-height:1.1;font-weight:700;letter-spacing:-.5px;font-variant-numeric:tabular-nums}.v small{font-size:13px;color:var(--mute);font-weight:400;margin-left:4px}
.row{display:flex;justify-content:space-between;gap:8px;font-variant-numeric:tabular-nums;font-size:12px;border-top:1px solid var(--line);padding-top:3px}.row b{font-weight:600}
.mart-list{max-height:150px;overflow-y:auto;min-height:0}
.note{color:var(--mute);font-size:12px;margin-top:auto}
.bars{display:flex;gap:6px;align-items:flex-end;height:48px;padding-top:4px}.bar{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:3px;font-size:11px;font-variant-numeric:tabular-nums}.bar i{display:block;width:100%;background:linear-gradient(180deg,var(--acc-light),var(--acc));border-radius:6px 6px 2px 2px;min-height:3px;transition:height .35s}
.bottom{display:grid;grid-template-columns:2fr 1fr;gap:10px;margin-top:10px}@media(max-width:1100px){.flow{grid-template-columns:1fr}.stage{margin-right:0}.stage::after{display:none}.bottom{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px}canvas{width:100%;height:92px;display:block}
ul{list-style:none;margin:4px 0 0;padding:0;max-height:104px;overflow:auto}li{display:grid;grid-template-columns:52px 1fr auto;gap:8px;padding:2px 0;font-size:12px;border-bottom:1px solid var(--line)}li .t{color:var(--mute)}
.pill{display:inline-block;padding:0 7px;border-radius:999px;font-size:11px;background:var(--acc-light);color:var(--brown);margin-left:6px}.pill.pa{background:#F7D9E0}.pill.re{background:#EEE}
.ok{color:var(--acc-deep);font-weight:600}.off{color:var(--pink);font-weight:600}a{color:var(--brown)}
</style></head><body>
<h1>HWABUN — 데이터 파이프라인 현황</h1>
<div class="top"><div class="sub">사이트 → Kafka → Spark → dw 마트 → 대시보드</div>
<div class="ctl">
 <label>초당 <select id="rate"><option>1000</option><option>2000</option><option selected>3000</option><option>5000</option><option>8000</option></select>건</label>
 <button id="start" class="btn">▶ 페르소나 시작</button><button id="stop" class="btn stop" hidden>■ 페르소나 정지</button>
 <span class="k" id="demo"></span>
 <label>런처 <input id="launcher" placeholder="http://127.0.0.1:8301"></label>
 <button id="agents" class="btn alt">▶ 에이전트 100명</button><span class="k" id="agstat"></span>
</div></div>
<div class="flow">
 <div class="stage" id="s1"><h2><span class="dot" id="d1"></span>① 사이트 활동</h2><div class="v" id="act">0<small>건</small></div><div class="k" id="act10"></div>
  <div class="row"><span>페르소나 <span class="pill">PC</span></span><b id="a_persona"></b></div>
  <div class="row"><span>에이전트 <span class="pill pa">PA</span></span><b id="a_agent"></b></div>
  <div class="row"><span>실사용자 <span class="pill re">회원</span></span><b id="a_real"></b></div>
  <div class="k" id="conv"></div></div>
 <div class="stage" id="s2"><h2><span class="dot" id="d2"></span>② Kafka 파티션</h2><div class="v" id="kend">0<small>건</small></div><div class="k" id="kpps"></div>
  <div class="bars" id="kbars"></div><div class="row"><span>추천 소비 위치</span><b id="kcom"></b></div><div class="row"><span>지연(lag)</span><b id="klag"></b></div>
  </div>
 <div class="stage" id="s3"><h2><span class="dot" id="d3"></span>③ Spark</h2><div class="v" id="spw">-<small>워커</small></div><div class="k" id="spc"></div><div id="spapps"></div>
  <div class="note" id="spnote"></div></div>
 <div class="stage" id="s4"><h2><span class="dot" id="d4"></span>④ dw 마트</h2><div class="v" id="dwn">-<small>마트</small></div><div class="k" id="dwt"></div><div class="mart-list" id="dwm"></div>
  <div class="note" id="dwnote"></div></div>
 <div class="stage" id="s5"><h2><span class="dot" id="d5"></span>⑤ 대시보드</h2><div class="v" id="rec">0<small>명 상태 반영</small></div><div class="k" id="rec2"></div>
  <div id="dash"></div>
  </div>
</div>
<div class="bottom">
 <div class="card"><div class="k">최근 60초 · 초당 사이트 활동 메시지</div><canvas id="spark" width="1200" height="92"></canvas></div>
 <div class="card"><div class="k">방금 상태가 바뀐 사용자</div><ul id="recent"></ul></div>
</div>
<script>
const $=id=>document.getElementById(id);const fmt=n=>(n==null?'-':Number(n).toLocaleString('ko-KR'));
function dot(id,st){const e=$(id);e.className='dot '+(st||'')}
function draw(series){const c=$('spark'),ctx=c.getContext('2d');const W=c.width,H=c.height;ctx.clearRect(0,0,W,H);const max=Math.max(1,...series);const bw=W/series.length;ctx.fillStyle='#A8C96E';series.forEach((v,i)=>{const h=Math.round(v/max*(H-16));ctx.fillRect(i*bw+1,H-h,Math.max(1,bw-2),h)});ctx.fillStyle='#6B7280';ctx.font='11px Pretendard,sans-serif';ctx.fillText('max '+max+'/s',4,12)}
async function tick(){try{const d=await (await fetch('/pipeline/stats',{cache:'no-store'})).json();
 const A=d.activity,ac=A.actors;$('act').innerHTML=fmt(A.total)+'<small>건</small>';$('act10').textContent='10초 평균 '+(ac.persona.per_sec_10s_avg+ac.agent.per_sec_10s_avg+ac.real.per_sec_10s_avg).toFixed(1)+'/s · 활동 주체 '+fmt(A.users)+'명';
 for(const a of ['persona','agent','real']){$('a_'+a).textContent=fmt(ac[a].users)+'명 · '+fmt(ac[a].total)+'건'+(ac[a].per_sec_10s_avg?(' · +'+ac[a].per_sec_10s_avg+'/s'):'')}
 const cv=['persona','agent','real'].reduce((o,a)=>{o.c+=ac[a].add_to_cart;o.k+=ac[a].begin_checkout;o.p+=ac[a].purchase;return o},{c:0,k:0,p:0});$('conv').textContent='담기 '+fmt(cv.c)+' · 결제 시작 '+fmt(cv.k)+' · 구매 '+fmt(cv.p);
 dot('d1',A.total?'ok':(d.kafka&&d.kafka.connected?'warn':'off'));
 const B=d.broker;if(B&&B.reachable){$('kend').innerHTML=fmt(B.end_total)+'<small>건</small>';$('kpps').textContent='초당 생산 '+fmt(B.produced_per_sec)+'/s · 파티션 '+Object.keys(B.partitions).length+'개';
  const ps=Object.keys(B.partitions);const mx=Math.max(1,...ps.map(p=>B.partitions[p].end));$('kbars').innerHTML=ps.map(p=>'<div class="bar"><span>'+fmt(B.partitions[p].end)+'</span><i style="height:'+Math.max(3,Math.round(B.partitions[p].end/mx*44))+'px"></i><span>P'+p+(B.partitions[p].lag?' <span style=color:var(--pink)>lag '+fmt(B.partitions[p].lag)+'</span>':'')+'</span></div>').join('');
  $('kcom').textContent=fmt(B.committed_total)+'건';$('klag').innerHTML=B.lag_total?'<span class=off>'+fmt(B.lag_total)+'</span>':'<span class=ok>0</span>';dot('d2','ok');$('s2').classList.remove('wait');}
 else{$('kpps').textContent=B&&B.configured?('브로커 조회 실패 · '+(B.error||'')):'KAFKA_BOOTSTRAP_SERVERS 없음';dot('d2',B&&B.configured?'off':'');$('s2').classList.add('wait');
  const k=d.kafka;if(k){$('kcom').textContent='소비자 processed '+fmt(k.processed);$('klag').textContent=k.lag==null?'-':fmt(k.lag);}}
 const S=d.spark;if(S&&S.reachable){$('spw').innerHTML=fmt(S.workers_alive)+'<small>워커 '+(S.status||'')+'</small>';$('spc').textContent='코어 '+S.cores_used+'/'+S.cores+' 사용 · 완료 앱 '+S.completed;
  $('spapps').innerHTML=(S.apps||[]).map(a=>'<div class="row"><span>'+a.name+'</span><b>'+a.state+' · '+Math.round(a.duration_sec/60)+'분</b></div>').join('')||'<div class="k">실행 중인 앱 없음</div>';dot('d3',(S.apps||[]).length?'ok':'warn');$('s3').classList.remove('wait');}
 else{$('spw').innerHTML='-<small>워커</small>';$('spc').textContent='';$('spapps').innerHTML='';$('spnote').textContent=S&&S.configured?('Spark UI 응답 없음 ('+S.url+') — EC2-2 가 127.0.0.1 에만 열어 두었다. 민우님께 EC2-1 사설 IP 개방 요청'):'SPARK_MASTER_UI 미설정 — 포트가 열리면 .env 에 넣는다';dot('d3',S&&S.configured?'off':'');$('s3').classList.add('wait');}
 const D=d.dw;if(D&&D.reachable){const ms=D.marts||{};const have=Object.keys(ms).filter(m=>ms[m]&&ms[m].rows>0);$('dwn').innerHTML=have.length+'<small>/'+Object.keys(ms).length+' 마트 채워짐</small>';$('dwt').textContent=(D.schema_exists?'dw 테이블 '+D.tables+'개':'dw 스키마 없음')+' · '+D.host;
  $('dwm').innerHTML=Object.keys(ms).map(m=>'<div class="row"><span>'+m.replace('_daily','').replace('_kpi','')+'</span><b>'+(ms[m]==null?'<span class=off>테이블 없음</span>':(fmt(ms[m].rows)+'행'+(ms[m].updated?(' · '+ms[m].updated.slice(5,16)):'')))+'</b></div>').join('');$('dwnote').textContent='';dot('d4',have.length?'ok':(D.schema_exists?'warn':'off'));$('s4').classList.remove('wait');}
 else{$('dwn').innerHTML='-<small>/'+Object.keys((D&&D.marts)||{}).length+' 마트</small>';$('dwt').textContent='';$('dwm').innerHTML='';$('dwnote').textContent=D&&D.configured?('dw 접속 실패 · '+(D.error||'')):'DW_MYSQL_HOST/USER 미설정 — 백엔드 dw 스키마·reader 계정 뒤 .env';dot('d4',D&&D.configured?'off':'');$('s4').classList.add('wait');}
 const L=d.live;$('rec').innerHTML=fmt(L.personas_touched)+'<small>명 상태 반영</small>';$('rec2').textContent='';
 $('dash').innerHTML=d.dashboard_url?'<div class="row"><span>대시보드</span><b><a href="'+d.dashboard_url+'" target="_blank">열기 ↗</a></b></div>':'<div class="k">DASHBOARD_URL 미설정</div>';dot('d5',L.personas_touched?'ok':'warn');
 draw(A.series_60s);const k=d.kafka;
 $('recent').innerHTML=(L.recent||[]).slice(0,30).map(r=>{const c=r.persona_id.startsWith('PA')?'pa':(r.persona_id.startsWith('PC')?'':'re');return '<li><span class="t">'+r.age_sec+'s 전</span><span>'+r.persona_id+'<span class="pill '+c+'">'+(c==='pa'?'에이전트':c==='re'?'회원':'페르소나')+'</span></span><span class="t">'+(r.events||[]).join(' · ')+'</span></li>'}).join('');
 showDemo(d.demo);}catch(e){}}
function showDemo(st){if(!st)return;const on=!!st.running;$('start').hidden=on;$('stop').hidden=!on;$('rate').disabled=on;if(st.limit)$('start').textContent='▶ 페르소나 '+fmt(st.limit)+'명 시작';if(!st.available){$('start').disabled=true;$('demo').textContent='시연 스크립트 없음';return}
 $('demo').textContent=on?'실행 중':''}
$('start').onclick=async()=>{$('start').disabled=true;try{await fetch('/live/demo/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rate:+$('rate').value})})}finally{$('start').disabled=false}tick()};
$('stop').onclick=async()=>{await fetch('/live/demo/stop',{method:'POST'});tick()};
const LK='hwabun.launcher';$('launcher').value=localStorage.getItem(LK)||'http://127.0.0.1:8301';$('launcher').onchange=()=>localStorage.setItem(LK,$('launcher').value);
async function agentStatus(){const base=$('launcher').value.replace(/\\/$/,'');try{const s=await (await fetch(base+'/status',{cache:'no-store'})).json();$('agstat').textContent=(s.running?'실행 중 · ':'')+(s.last_line||(s.running?'':'대기'));$('agents').disabled=!!s.running}catch(e){$('agstat').textContent='';$('agents').disabled=false}}
$('agents').onclick=async()=>{const base=$('launcher').value.replace(/\\/$/,'');if(!confirm('에이전트 100명을 배포 사이트에서 시작합니다.\\n\\nGMS 약 2,500회 호출 · 크레딧 약 1,500 · 한 시간쯤 걸립니다 (09-17 3명 실측에서 환산).\\n\\n진행할까요?'))return;try{const r=await fetch(base+'/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({limit:100})});const j=await r.json();$('agstat').textContent=j.ok?'시작됨':('거절: '+(j.error||''))}catch(e){$('agstat').textContent='런처에 연결 못 함'}agentStatus()};
tick();setInterval(tick,1000);agentStatus();setInterval(agentStatus,3000);
</script></body></html>
"""
