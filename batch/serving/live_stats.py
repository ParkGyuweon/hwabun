# -*- coding: utf-8 -*-
"""
실시간 처리 현황 카운터 (Jira 295, 2026-09-14) — `GET /live` · `GET /live/stats` 가 읽는다
================================================================================

무엇을 보여주는가
    시연에서 "페르소나 9,900명 트래픽이 쏟아져도 상태가 실시간으로 갱신된다" 를 눈으로 보이게
    하는 숫자들이다. 상태를 바꾸는 이벤트가 **어디서**(Kafka 파티션 / 직접 HTTP) **얼마나**(초당)
    들어오고, 그 결과 **누구의**(persona_id) 상태가 방금 바뀌었고, 추천 요청이 몇 ms 에 나가는지.

왜 서버 안 카운터인가
    Grafana 는 수집기(8080)까지만 보고, Spark UI 는 마트까지만 본다. "그 이벤트가 추천 상태에
    반영됐다" 는 마지막 층은 이 프로세스만 안다. 그래서 여기서 센다. Prometheus 노출은 하지 않는다 —
    시연용 한 페이지가 목적이고, 운영 지표는 수집기 쪽 메트릭이 정본이다.

비용
    이벤트당 deque append 한 번. 60초 링 밖은 snapshot 때 버린다. 락은 짧다.
"""
from __future__ import annotations

import threading
import time
from collections import Counter, deque

WINDOW_SEC = 120          # 초당 시계열을 이만큼 보관
RECENT_MAX = 40           # "방금 상태가 바뀐 사람" 목록 길이


class LiveStats:
    def __init__(self, window=WINDOW_SEC, recent=RECENT_MAX):
        self.window = window
        self.lock = threading.Lock()
        self.started_at = time.time()
        self._events = deque()          # (ts, n_events)
        self._recs = deque()            # (ts, latency_ms)
        self.recent = deque(maxlen=recent)
        self.total_events = 0
        self.total_recommends = 0
        self.event_names = Counter()
        self.sources = Counter()        # "kafka" / "http"
        self.partitions = Counter()     # Kafka 파티션 번호 -> 이벤트 수 (Kafka 로 들어온 것만)
        self.personas_touched = set()

    # ── 기록 ────────────────────────────────────────────────────────────
    def record_events(self, persona_id, events, source="http", partition=None):
        if not events or source == "replay":       # 기동 시 세션 로그 재생은 "지금 들어온 것" 이 아니다
            return
        now = time.time()
        names = [e.get("event_name") if isinstance(e, dict) else str(e) for e in events]
        with self.lock:
            self._events.append((now, len(events), (int(partition) if partition is not None else None)))
            self.total_events += len(events)
            self.event_names.update(names)
            self.sources[source] += len(events)
            if partition is not None:
                self.partitions[int(partition)] += len(events)
            self.personas_touched.add(persona_id)
            self.recent.append({"ts": now, "persona_id": persona_id, "n": len(events),
                                "events": names[-3:], "source": source, "partition": partition})
            self._trim(now)

    def record_partitions(self, counts):
        """Kafka 소비자가 배치마다 넘기는 {파티션: 메시지 수}. 이벤트 자체는 record_events 로 센다"""
        if not counts:
            return
        with self.lock:
            for p, n in counts.items():
                self.partitions[int(p)] += int(n)

    def record_recommend(self, persona_id, latency_ms):
        now = time.time()
        with self.lock:
            self._recs.append((now, float(latency_ms)))
            self.total_recommends += 1
            self._trim(now)

    def _trim(self, now):
        lim = now - self.window
        while self._events and self._events[0][0] < lim:
            self._events.popleft()
        while self._recs and self._recs[0][0] < lim:
            self._recs.popleft()

    # ── 읽기 ────────────────────────────────────────────────────────────
    def snapshot(self, seconds=60):
        now = time.time()
        with self.lock:
            self._trim(now)
            series = [0] * seconds                  # series[-1] = 지금 이 1초
            ev_1s = ev_10s = 0
            part_1s, part_10s = Counter(), Counter()
            for ts, n, part in self._events:
                age = now - ts
                idx = seconds - 1 - int(age)
                if 0 <= idx < seconds:
                    series[idx] += n
                if age < 1:
                    ev_1s += n
                    if part is not None:
                        part_1s[part] += n
                if age < 10:
                    ev_10s += n
                    if part is not None:
                        part_10s[part] += n
            rec_10s = [l for ts, l in self._recs if now - ts < 10]
            rec_60s = [l for ts, l in self._recs if now - ts < 60]
            lat = sorted(rec_60s)
            p50 = lat[len(lat) // 2] if lat else None
            p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None
            recent = [dict(r, age_sec=round(now - r["ts"], 1)) for r in reversed(self.recent)]
            return {
                "now": now, "uptime_sec": round(now - self.started_at),
                "events": {"per_sec": ev_1s, "per_sec_10s_avg": round(ev_10s / 10.0, 1),
                           "series_60s": series, "total": self.total_events,
                           "by_name": dict(self.event_names.most_common(8)),
                           "by_source": dict(self.sources)},
                "partitions": {str(k): v for k, v in sorted(self.partitions.items())},
                "partitions_rate": {str(k): {"per_sec": part_1s.get(k, 0), "per_sec_10s_avg": round(part_10s.get(k, 0) / 10.0, 1)}
                                    for k in sorted(self.partitions)},
                "personas_touched": len(self.personas_touched),
                "recommend": {"per_sec_10s_avg": round(len(rec_10s) / 10.0, 2),
                              "total": self.total_recommends,
                              "p50_ms": (round(p50, 1) if p50 is not None else None),
                              "p95_ms": (round(p95, 1) if p95 is not None else None)},
                "recent": recent,
            }


LIVE_HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>HWABUN 추천 서버 — 실시간 처리 현황</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>
/* HWABUN 팔레트: Fresh Green #A8C96E · Soft Mint #D8E9C3 · Blossom Pink #E68FA1 · Earthy Brown #7A5B43 · Warm Ivory #FAF7F1 · Light Gray #E9ECEF · Charcoal #2B2B2B · Soft Gray #6B7280 */
:root{--bg:#FAF7F1;--card:#FFFFFF;--line:#E9ECEF;--fg:#2B2B2B;--mute:#6B7280;--acc:#A8C96E;--acc-light:#D8E9C3;--acc-deep:#7FA34A;--pink:#E68FA1;--brown:#7A5B43;--acc2:#A8C96E;--bad:#E68FA1}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 'Pretendard','Apple SD Gothic Neo','Helvetica Neue',Helvetica,Arial,'Malgun Gothic',sans-serif;padding:18px 24px;min-height:100vh;max-width:1880px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px;font-weight:700;color:var(--brown)}.sub{color:var(--mute);margin-bottom:14px;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 18px;box-shadow:0 1px 2px rgba(43,43,43,.04)}
.k{color:var(--mute);font-size:12px}.v{font-size:34px;line-height:1.2;font-weight:700;letter-spacing:-.5px;font-variant-numeric:tabular-nums;color:var(--fg)}
.v small{font-size:13px;color:var(--mute);font-weight:400;margin-left:4px}
.main{display:grid;grid-template-columns:1fr 2fr;gap:12px;margin-top:12px;align-items:stretch}.right{display:flex;flex-direction:column;gap:12px}.left{display:flex;flex-direction:column;min-height:0}.left ul{flex:1 1 0;min-height:0;height:0;max-height:none;overflow:auto}@media(max-width:1000px){.main{grid-template-columns:1fr}}
canvas{width:100%;height:170px;display:block}
.bars{display:flex;gap:10px;align-items:flex-end;height:120px;padding-top:8px}.bars.big{height:330px;overflow:hidden;gap:40px;padding:8px 40px 0;max-width:1000px;margin:0 auto}.bars.big .bar span{font-size:28px;font-weight:700}.bars.big .bar em{font-size:15px}.bars.big .bar b{font-size:15px}.bars.big .bar em{font-style:normal;font-size:13px;color:var(--acc-deep);font-weight:600}.bars.big .bar b{font-size:14px}
.bar{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:6px;font-variant-numeric:tabular-nums;min-height:0}.bar span,.bar em,.bar b{line-height:1.25;white-space:nowrap}
.bar i{display:block;width:100%;background:linear-gradient(180deg,var(--acc-light),var(--acc));border-radius:8px 8px 3px 3px;min-height:3px;transition:height .35s ease-out;box-shadow:0 0 0 1px rgba(122,91,67,.12) inset}
.bar b{font-size:12px;color:var(--brown);font-weight:600}
ul{list-style:none;margin:6px 0 0;padding:0;max-height:560px;overflow:auto}
li{display:grid;grid-template-columns:64px 1fr auto;gap:10px;padding:6px 0;font-size:14px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
li .t{color:var(--mute)}li .e{color:var(--mute);font-size:12px}
li{border-bottom:1px solid var(--line)}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;background:var(--acc-light);color:var(--brown);margin-left:6px}
.ok{color:var(--acc-deep);font-weight:600}.off{color:var(--pink);font-weight:600}
.top{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:14px}.top .sub{margin:0}.ctl{display:flex;align-items:center;gap:10px}.ctl label{color:var(--mute);font-size:13px}.ctl select{font:inherit;padding:4px 8px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--fg)}
.btn{font:inherit;font-weight:700;font-size:15px;padding:9px 18px;border:0;border-radius:999px;background:var(--acc);color:#fff;cursor:pointer;box-shadow:0 2px 6px rgba(168,201,110,.35)}.btn:hover{background:var(--acc-deep)}.btn.stop{background:var(--pink)}.btn:disabled{opacity:.5;cursor:default}
</style></head><body>
<h1>HWABUN 추천 서버 — 실시간 처리 현황</h1>
<div class="top"><div class="sub">1초마다 갱신 · <span id="kafka"></span></div>
<div class="ctl" id="ctl"><label>초당 <select id="rate"><option>1000</option><option>2000</option><option selected>3000</option><option>5000</option><option>8000</option></select>건</label>
<button id="start" class="btn">▶ 페르소나 시작</button><button id="stop" class="btn stop" hidden>■ 정지</button><span class="k" id="demo"></span></div></div>
<div class="grid">
  <div class="card"><div class="k">초당 반영 이벤트</div><div class="v" id="eps">0<small>/s</small></div><div class="k" id="eps10"></div></div>
  <div class="card"><div class="k">누적 반영 이벤트</div><div class="v" id="total">0</div><div class="k" id="src"></div></div>
  <div class="card"><div class="k">상태가 바뀐 사용자</div><div class="v" id="personas">0<small>명</small></div><div class="k">메모리 세션 <span id="mem">-</span></div></div>
  <div class="card"><div class="k">추천 응답</div><div class="v" id="p50">-<small>ms p50</small></div><div class="k" id="rec"></div></div>
</div>
<div class="main">
  <div class="card left"><div class="k">방금 상태가 바뀐 사용자</div><ul id="recent"></ul></div>
  <div class="right">
    <div class="card"><div class="k">최근 60초 · 초당 이벤트</div><canvas id="spark" width="1200" height="170"></canvas></div>
    <div class="card"><div class="k">Kafka 파티션별 소비 <span style="color:var(--mute)">· 막대 = 최근 10초 처리량 · 숫자 = 누적 · key = session_id</span></div><div class="bars big" id="bars"></div><div class="k" id="barnote"></div></div>
  </div>
</div>
<script>
const $=id=>document.getElementById(id);
function fmt(n){return (n||0).toLocaleString('ko-KR')}
function draw(series){const c=$('spark'),ctx=c.getContext('2d');const W=c.width,H=c.height;ctx.clearRect(0,0,W,H);
 const max=Math.max(1,...series);const bw=W/series.length;ctx.fillStyle='#A8C96E';
 series.forEach((v,i)=>{const h=Math.round(v/max*(H-16));ctx.fillRect(i*bw+1,H-h,Math.max(1,bw-2),h)});
 ctx.fillStyle='#6B7280';ctx.font='11px Pretendard, sans-serif';ctx.fillText('max '+max+'/s',4,12)}
async function tick(){try{const r=await fetch('/live/stats',{cache:'no-store'});const d=await r.json();
 $('eps').innerHTML=fmt(d.events.per_sec)+'<small>/s</small>';$('eps10').textContent='10초 평균 '+d.events.per_sec_10s_avg+'/s';
 $('total').textContent=fmt(d.events.total);const s=d.events.by_source||{};$('src').textContent='Kafka '+fmt(s.kafka)+' · 직접 '+fmt(s.http);
 $('personas').innerHTML=fmt(d.personas_touched)+'<small>명</small>';$('mem').textContent=fmt(d.sessions_in_memory);
 $('p50').innerHTML=(d.recommend.p50_ms==null?'-':d.recommend.p50_ms)+'<small>ms p50</small>';
 $('rec').textContent='p95 '+(d.recommend.p95_ms==null?'-':d.recommend.p95_ms+'ms')+' · '+d.recommend.per_sec_10s_avg+' 요청/s · 누적 '+fmt(d.recommend.total);
 draw(d.events.series_60s); showDemo(d);
 const k=d.kafka;$('kafka').innerHTML=k?('Kafka '+(k.connected?'<span class="ok">연결</span>':'<span class="off">미연결</span>')+' · 토픽 '+k.topic+' · lag '+(k.lag==null?'-':k.lag)):'Kafka 구독 없음(직접 수신만)';
 const parts=d.partitions||{};const rates=d.partitions_rate||{};const keys=Object.keys(parts);const bars=$('bars');
 if(keys.length){const r10=x=>(rates[x]||{}).per_sec_10s_avg||0;const mx=Math.max(1,...keys.map(r10));
  bars.innerHTML=keys.map(x=>'<div class="bar"><span>'+fmt(parts[x])+'</span><em>+'+fmt(Math.round(r10(x)))+'/s</em><i style="height:'+Math.max(3,Math.round(r10(x)/mx*196))+'px"></i><b>파티션 P'+x+'</b></div>').join('');
  const tot=keys.reduce((a,x)=>a+parts[x],0);$('barnote').textContent='파티션 '+keys.length+'개 · 누적 '+fmt(tot)+' · 가장 많이 받은 파티션 '+Math.round(Math.max(...keys.map(x=>parts[x]))/Math.max(1,tot)*100)+'%';}
 else{bars.innerHTML='';$('barnote').textContent=k?'아직 Kafka 로 들어온 이벤트가 없다':'Kafka 구독이 꺼져 있어 파티션 정보가 없다 (KAFKA_BOOTSTRAP_SERVERS)';}
 $('recent').innerHTML=(d.recent||[]).map(r=>'<li><span class="t">'+r.age_sec+'s 전</span><span>'+r.persona_id+'<span class="pill">'+(r.source==='kafka'?'P'+(r.partition==null?'?':r.partition):'직접')+'</span></span><span class="e">'+(r.events||[]).join(' · ')+'</span></li>').join('');
}catch(e){$('kafka').innerHTML='<span class="off">서버 응답 없음</span>'}}
function showDemo(d){const st=d&&d.demo;if(!st)return;const on=!!st.running;$('start').hidden=on;$('stop').hidden=!on;$('rate').disabled=on;if(st.limit)$('start').textContent='▶ 페르소나 '+fmt(st.limit)+'명 시작';
 if(!st.available){$('start').disabled=true;$('demo').textContent='이 서버엔 시연 스크립트가 없다 (로컬 체크아웃에서만)';return;}
 $('demo').textContent=on?('실행 중 · '+(st.last_line||'').replace('[demo] ','')):(st.exit_code==null?'':'끝남 · '+(st.last_line||'').replace('[demo] ',''));}
$('start').onclick=async()=>{$('start').disabled=true;try{await fetch('/live/demo/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rate:+$('rate').value})});}finally{$('start').disabled=false;}tick();};
$('stop').onclick=async()=>{await fetch('/live/demo/stop',{method:'POST'});tick();};
tick();setInterval(tick,1000);
</script></body></html>
"""



# ── 상태가 바뀐 사용자만 크게 보여 주는 한 페이지 (2026-09-21) ────────────────
# 시연을 컴퓨터 세 대로 나눠 하면서 "이 화면만 따로 띄우고 싶다" 는 요청으로 만들었다.
# /live 와 같은 /live/stats 를 읽는다 — 새 API 를 만들지 않는다.
USERS_HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>상태가 바뀐 사용자</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#faf8f5;--fg:#2b2622;--mute:#8b8179;--line:#e8e1d9;--acc:#a8c96e;--acc-deep:#7d9c46;--acc-light:#eef4e0;--brown:#7a5b43;--card:#fff}
*{box-sizing:border-box}
body{margin:0;padding:22px 26px;background:var(--bg);color:var(--fg);
 font:15px/1.5 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
h1{margin:0 0 4px;font-size:22px;letter-spacing:-.4px}
.sub{margin:0 0 16px;color:var(--mute);font-size:13px}
.head{display:flex;align-items:baseline;gap:26px;margin-bottom:14px}
.big{font-size:64px;font-weight:700;letter-spacing:-2px;font-variant-numeric:tabular-nums;line-height:1}
.big small{font-size:18px;color:var(--mute);font-weight:400;margin-left:6px}
.k{color:var(--mute);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
ul{list-style:none;margin:8px 0 0;padding:0}
li{display:grid;grid-template-columns:84px 1fr;gap:14px;padding:10px 2px;border-bottom:1px solid var(--line);
 font-variant-numeric:tabular-nums;animation:in .35s ease-out}
li:first-child{background:linear-gradient(90deg,var(--acc-light),transparent);border-radius:8px}
@keyframes in{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}
.t{color:var(--mute);font-size:14px}
.who{font-size:17px;font-weight:600;letter-spacing:-.2px;word-break:break-all}
.ev{color:var(--mute);font-size:13px;margin-top:3px}
.pill{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;
 background:var(--acc-light);color:var(--brown);margin-left:8px;font-weight:600}
.n{color:var(--acc-deep);font-weight:700;margin-left:8px}
</style></head><body>
<h1>방금 상태가 바뀐 사용자</h1>
<p class="sub">이벤트가 추천 상태에 반영된 사람이 실시간으로 올라옵니다 · 1초마다 갱신</p>
<div class="head">
  <div><div class="k">상태가 바뀐 사용자</div><div class="big" id="personas">0<small>명</small></div></div>
  <div><div class="k">초당 반영 이벤트</div><div class="big" id="eps">0<small>/s</small></div></div>
  <div><div class="k">누적 반영</div><div class="big" id="total">0</div></div>
</div>
<div class="card"><ul id="recent"></ul></div>
<script>
var $ = function(id){ return document.getElementById(id); };
var fmt = function(n){ return (n == null ? 0 : n).toLocaleString(); };
function draw(d){
  $("personas").innerHTML = fmt(d.personas_touched) + "<small>명</small>";
  var ev = d.events || {};
  $("eps").innerHTML = fmt(ev.per_sec_10s_avg) + "<small>/s</small>";
  $("total").textContent = fmt(ev.total);
  var rows = d.recent || [];
  $("recent").innerHTML = rows.map(function(r){
    var src = r.source === "kafka" ? ("P" + (r.partition == null ? "?" : r.partition)) : "직접";
    var events = (r.events || []).join(" · ");
    return "<li><span class=\"t\">" + r.age_sec + "s 전</span>" +
           "<span><span class=\"who\">" + r.persona_id + "</span>" +
           "<span class=\"pill\">" + src + "</span>" +
           "<span class=\"n\">+" + r.n + "</span>" +
           "<div class=\"ev\">" + events + "</div></span></li>";
  }).join("");
}
function tick(){
  fetch("/live/stats").then(function(r){ return r.json(); }).then(draw).catch(function(){});
}
tick();
setInterval(tick, 1000);
</script>
</body></html>"""


def log_tail(path, nbytes=400):
    """로그 파일의 마지막 줄 (Jira 344).

    끝에서 nbytes 만 읽되, 그 경계는 UTF-8 한글(3바이트) 중간에 걸릴 수 있다. 예전 코드는 그때
    UnicodeDecodeError 를 cp949 폴백으로 받아 꼬리 전체가 "蹂닿린" 꼴로 깨졌다. 잘린 첫 조각(첫 줄바꿈 이전)을
    버리고 UTF-8 로만 읽는다 — demo_live 는 컨테이너에서 PYTHONIOENCODING=utf-8 로 쓰므로 다른 인코딩은 없다."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); n = f.tell(); start = max(0, n - nbytes); f.seek(start)
            raw = f.read()
    except OSError:
        return ""
    if start > 0 and b"\n" in raw:
        raw = raw.split(b"\n", 1)[1]                   # 앞의 잘린 조각은 버린다 (마지막 줄만 쓴다)
    lines = [ln for ln in raw.decode("utf-8", "replace").splitlines() if ln.strip()]
    return lines[-1].strip() if lines else ""

