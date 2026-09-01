// 이벤트·행동 로그 문서를 한 페이지로 묶는다.
//
// 설명·KPI 는 event-taxonomy-trigger-schema.md §6 에서, 가중치 숫자는
// frontend/src/types/log.ts 에서 그때그때 읽는다. 어느 쪽도 이 파일에
// 복사해 두지 않는다 — 복사해 두면 원본이 바뀔 때 조용히 어긋난다.
//
// 실행 (레포 루트에서)
//   node docs/analytics/tools/build-event-guide.mjs
//   -> docs/analytics/event-guide.html
//
// 의존성 없음. Node 18+ 면 된다.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..', '..');
const OUT = path.join(ROOT, 'docs', 'analytics', 'event-guide.html');

// 최소 GFM 변환기. 이 레포 문서가 쓰는 문법만 다룬다.
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function inline(s){
  const code=[];
  s=s.replace(/`([^`]+)`/g,(m,c)=>{code.push(c);return '\u0000C'+(code.length-1)+'\u0000';});
  s=esc(s);
  s=s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g,(m,t,h)=>`<a href="${h}">${t}</a>`);
  s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
  s=s.replace(/(^|[^*])\*([^*\n]+)\*/g,'$1<em>$2</em>');
  s=s.replace(/\u0000C(\d+)\u0000/g,(m,i)=>`<code>${esc(code[+i])}</code>`);
  return s;
}

function slug(s,used){
  let b=s.toLowerCase().replace(/[`*]/g,'').trim()
        .replace(/[^\w\uac00-\ud7a3\s-]/g,'').replace(/\s+/g,'-');
  if(!b)b='s';
  let k=b,n=2; while(used.has(k)){k=b+'-'+(n++);} used.add(k); return k;
}

const BS=String.fromCharCode(92);
function cells(line){
  let t=line.trim().replace(/^\|/,'').replace(/\|$/,'');
  const out=[]; let cur='';
  for(let i=0;i<t.length;i++){
    if(t[i]===BS&&t[i+1]==='|'){cur+='|';i++;continue;}
    if(t[i]==='|'){out.push(cur);cur='';continue;}
    cur+=t[i];
  }
  out.push(cur); return out.map(c=>c.trim());
}
const isDiv=l=>/^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(l)&&l.includes('-');

function render(md){
  const lines=md.replace(/\r\n/g,'\n').split('\n');
  const used=new Set(); const toc=[]; const out=[];
  let i=0;
  const listStack=[];
  function closeLists(to){ while(listStack.length>to){ out.push('</'+listStack.pop()+'>'); } }

  while(i<lines.length){
    const line=lines[i];

    if(/^```/.test(line)){
      closeLists(0);
      const lang=line.slice(3).trim(); const buf=[]; i++;
      while(i<lines.length&&!/^```/.test(lines[i])){buf.push(lines[i]);i++;}
      i++;
      out.push(`<pre class="code"${lang?` data-lang="${esc(lang)}"`:''}><code>${esc(buf.join('\n'))}</code></pre>`);
      continue;
    }

    const h=line.match(/^(#{1,6})\s+(.*)$/);
    if(h){
      closeLists(0);
      const lv=h[1].length, txt=h[2].trim(), id=slug(txt,used);
      if(lv<=3) toc.push({lv,txt:txt.replace(/[`*]/g,''),id});
      out.push(`<h${lv} id="${id}">${inline(txt)}</h${lv}>`);
      i++; continue;
    }

    if(line.includes('|')&&i+1<lines.length&&isDiv(lines[i+1])){
      closeLists(0);
      const head=cells(line); i+=2; const rows=[];
      while(i<lines.length&&lines[i].includes('|')&&lines[i].trim()){rows.push(cells(lines[i]));i++;}
      out.push('<div class="tw"><table><thead><tr>'+head.map(c=>`<th>${inline(c)}</th>`).join('')
        +'</tr></thead><tbody>'+rows.map(r=>'<tr>'+head.map((_,x)=>`<td>${inline(r[x]??'')}</td>`).join('')+'</tr>').join('')
        +'</tbody></table></div>');
      continue;
    }

    if(/^\s*(---+|___+|\*\*\*+)\s*$/.test(line)){closeLists(0);out.push('<hr>');i++;continue;}

    if(/^\s*>/.test(line)){
      closeLists(0); const buf=[];
      while(i<lines.length&&/^\s*>/.test(lines[i])){buf.push(lines[i].replace(/^\s*>\s?/,''));i++;}
      const inner=render(buf.join('\n'));
      out.push('<blockquote>'+inner.html+'</blockquote>');
      continue;
    }

    const li=line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if(li){
      const depth=Math.floor(li[1].replace(/\t/g,'  ').length/2);
      const tag=/\d/.test(li[2])?'ol':'ul';
      while(listStack.length>depth+1) out.push('</'+listStack.pop()+'>');
      if(listStack.length<depth+1){ out.push('<'+tag+'>'); listStack.push(tag); }
      const buf=[li[3]]; i++;
      while(i<lines.length&&/^\s+\S/.test(lines[i])&&!/^\s*([-*+]|\d+[.)])\s/.test(lines[i])&&!/^```/.test(lines[i].trim())){
        buf.push(lines[i].trim()); i++;
      }
      out.push('<li>'+inline(buf.join(' '))+'</li>');
      continue;
    }

    if(!line.trim()){ closeLists(0); i++; continue; }

    closeLists(0);
    const buf=[line]; i++;
    while(i<lines.length&&lines[i].trim()&&!/^(#{1,6}\s|```|\s*>|\s*([-*+]|\d+[.)])\s)/.test(lines[i])
          &&!(lines[i].includes('|')&&i+1<lines.length&&isDiv(lines[i+1]))
          &&!/^\s*(---+|___+)\s*$/.test(lines[i])){ buf.push(lines[i]); i++; }
    out.push('<p>'+inline(buf.join('\n')).replace(/\n/g,'<br>')+'</p>');
  }
  closeLists(0);
  return {html:out.join('\n'),toc};
}

// PM 이 바로 보는 두 문서를 만든다.
//
// 설명·KPI 는 taxonomy §6 표에서, 가중치 숫자는 log.ts 에서 그때그때 읽는다.
// 어느 쪽도 여기에 복사해 두지 않는다 — 복사해 두면 원본이 바뀔 때 조용히 어긋난다.

// §6 표에 설명 행이 없는 이벤트. 없으면 표에서 빠지므로 여기서 채운다.
// (계약 문서에 채워지면 이 목록은 지운다)
const FILL = {
  impression_dwell: {
    intent: 'exposure',
    desc: '상품 카드가 화면에 얼마나 오래 머물렀는지',
    kpi: '스쳐 지나간 것과 눈이 멈춘 것을 가른다',
  },
  recommendation_snapshot: {
    intent: 'exposure',
    desc: '추천 목록에 어떤 상품이 몇 번째로 떴는지 통째로 기록',
    kpi: '"위에 있어서 눌렀나" 를 나중에 보정한다',
  },
  variant_select: {
    intent: 'comparison',
    desc: '색상·용량 같은 옵션을 고른 것',
    kpi: '어떤 옵션이 인기인지',
  },
};

// 딱딱한 말을 쉬운 말로 바꾼다. 뜻이 달라지지 않는 것만 손댄다.
// 문서의 용어를 임의로 바꾸지 않는다. 계약 문서 표기를 그대로 쓴다.
const SOFTEN = [];

function parseSix() {
  const md = fs.readFileSync(
    path.join(ROOT, 'docs/analytics/event-taxonomy-trigger-schema.md'), 'utf8')
    .replace(/\r\n/g, '\n').split('\n');
  const rows = [];
  let section = null, inSix = false;
  const ROW = /^\|\s*`([a-z_]+)`\s*\|\s*`?([a-z_]+)`?\s*\|([^|]*)\|([^|]*)\|\s*$/;
  for (const line of md) {
    const h2 = line.match(/^##\s+(\d+)\./);
    if (h2) { inSix = h2[1] === '6'; section = null; continue; }
    if (!inSix) continue;
    const h3 = line.match(/^###\s+6\.\d+\s+(.*)$/);
    if (h3) { section = h3[1].trim(); continue; }
    const m = line.match(ROW);
    if (!m || !section) continue;
    rows.push({ name: m[1], intent: m[2], desc: m[3].trim(), kpi: m[4].trim(), section });
  }
  return rows;
}

function parseWeights() {
  const ts = fs.readFileSync(path.join(ROOT, 'frontend/src/types/log.ts'), 'utf8');
  const block = ts.match(/EVENT_WEIGHT[^=]*=\s*\{([\s\S]*?)\n\};/);
  if (!block) throw new Error('log.ts 에서 EVENT_WEIGHT 를 못 읽었다');
  const w = {};
  for (const m of block[1].matchAll(/^\s*([a-z_]+)\s*:\s*([\d.]+)\s*,/gm)) {
    w[m[1]] = parseFloat(m[2]);
  }
  if (!Object.keys(w).length) throw new Error('EVENT_WEIGHT 항목을 못 읽었다');
  return w;
}

const escS = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
function soften(s) {
  let t = String(s);
  for (const [re, to] of SOFTEN) t = t.replace(re, to);
  return t;
}
const rich = s => escS(soften(s)).replace(/`([^`]+)`/g, '<code>$1</code>');

// ── 문서 1. 이벤트와 가중치 ──────────────────────────────────────────────
function buildEvents() {
  const contract = JSON.parse(fs.readFileSync(
    path.join(ROOT, 'contracts/event-schema.json'), 'utf8'))
    .properties.event_name.enum;
  const inContract = new Set(contract);

  const weights = parseWeights();
  const seen = new Set();
  const rows = parseSix()
    .filter(r => inContract.has(r.name))
    .filter(r => !seen.has(r.name) && seen.add(r.name));

  const filled = [];
  for (const name of contract) {
    if (seen.has(name) || !FILL[name]) continue;
    const f = FILL[name];
    const section = f.intent === 'exposure'
      ? 'Product Exposure / Exploration' : 'Product Detail Engagement';
    rows.push({ name, ...f, section });
    seen.add(name);
    filled.push(name);
  }

  const bySection = new Map();
  for (const r of rows) {
    if (!bySection.has(r.section)) bySection.set(r.section, []);
    bySection.get(r.section).push(r);
  }

  const positive = contract.filter(n => (weights[n] ?? 0) > 0);
  const zero = contract.filter(n => (weights[n] ?? 0) === 0);
  const maxW = Math.max(...contract.map(n => weights[n] ?? 0));
  const cls = w => w === 0 ? 'w0' : w >= 3 ? 'w3' : w >= 1.5 ? 'w2' : 'w1';

  let h = '';
  h += `<h1 id="ev-top">이벤트 ${contract.length}종과 가중치</h1>`;
  h += `<p class="lead">테스트 쇼핑몰에서 사용자가 남기는 행동 신호를 `
     + `<strong>Event</strong> 라 부른다. 현재 계약에 ${contract.length}종이 정의돼 있고, `
     + `각 Event 에는 <strong>선호도 가중치</strong>가 붙는다. 이 가중치를 누적해 `
     + `사용자 벡터를 만들고, 상품 추천(CBF)의 입력으로 쓴다.</p>`;

  h += `<div class="kpirow">`
     + `<div class="kpi"><b>${contract.length}</b><span>계약 Event</span></div>`
     + `<div class="kpi"><b>${positive.length}</b><span>선호도에 반영</span></div>`
     + `<div class="kpi"><b>${zero.length}</b><span>가중 0 · 분모·요약용</span></div>`
     + `<div class="kpi"><b>${maxW.toFixed(1)}</b><span>최대 가중치</span></div>`
     + `</div>`;

  h += `<h2 id="ev-weight">가중치 설계 원칙</h2>`;
  h += `<ul>`
     + `<li><strong>전환 신호가 가장 높다.</strong> `
     + `<code>add_to_cart</code> ${(weights.add_to_cart ?? 4).toFixed(1)}. `
     + `구매 데이터가 없는 환경이라 장바구니 담기가 가장 강한 구매 의도 신호다.</li>`
     + `<li><strong>노출(impression)은 가중 0 이다.</strong> `
     + `사용자 의지가 아니므로 선호도에 넣지 않고, CTR 의 <strong>분모</strong>로만 쓴다.</li>`
     + `<li><strong>이중 계상을 막는다.</strong> 한 행동에서 두 Event 가 같은 `
     + `<code>product_id</code> 를 실으면 한쪽을 0 으로 둔다. 상세 진입은 `
     + `<code>product_view</code>(1.0)가 담당하고 <code>page_view</code>는 0 이다. `
     + `<code>section_view</code>와 <code>section_dwell</code>도 같은 이유로 갈랐다.</li>`
     + `</ul>`;
  h += `<p class="note">확정값이 아니라 <strong>초기 가설</strong>이다. Ablation 으로 검증해 `
     + `조정한다. 가중치 상수의 단일 출처는 <code>frontend/src/types/log.ts</code> 의 `
     + `<code>EVENT_WEIGHT</code> 이고, 값별 근거는 `
     + `<code>docs/analytics/event-weight-rationale.html</code> 에 있다.</p>`;

  for (const [section, list] of bySection) {
    h += `<h2 id="ev-${escS(section).replace(/[^\w]/g, '-')}">${escS(section)}`
       + `<span class="cnt">${list.length}종</span></h2>`;
    h += `<div class="tw"><table><thead><tr>`
       + `<th>event_name</th><th>가중치</th><th>설명</th><th>주요 KPI · 활용</th>`
       + `</tr></thead><tbody>`;
    for (const r of list) {
      const w = weights[r.name] ?? 0;
      h += `<tr><td><code>${escS(r.name)}</code></td>`
         + `<td><span class="wt ${cls(w)}">${w === 0 ? '0' : w.toFixed(1)}</span></td>`
         + `<td>${rich(r.desc)}</td><td class="dim">${rich(r.kpi)}</td></tr>`;
    }
    h += `</tbody></table></div>`;
  }

  if (filled.length) {
    h += `<p class="note"><strong>계약 문서 보완 필요.</strong> `
       + filled.map(n => `<code>${escS(n)}</code>`).join(', ')
       + ` ${filled.length}종은 §6 설명 표에 행이 없다. §9 필수 property 표에는 있으므로 `
       + `Event 자체가 빠진 것은 아니고 설명만 비어 있어, 이 페이지에서 임시로 채웠다.</p>`;
  }
  return h;
}

// ── 문서 2. 수집 파이프라인 ──────────────────────────────────────────────
function buildFlow() {
  let h = '';
  h += `<h1 id="fl-top">Event 수집 파이프라인</h1>`;
  h += `<p class="lead">화면에서 발생한 Event 가 B2B Dashboard 까지 가는 경로다. `
     + `단계별 역할과 현재 구현 상태를 함께 적는다.</p>`;

  const steps = [
    ['1', '테스트 쇼핑몰 (FE)',
      '사용자 또는 가상 소비자가 상품을 탐색·비교·담는다. 화면의 로거가 각 행동을 LogEnvelope 로 조립한다.',
      'React 19 · 상품 목록 / 상품 상세 / 장바구니', 'done', '구현 완료'],
    ['2', '배치 전송',
      'Event 를 건별로 보내지 않는다. 20건이 쌓이거나 5초가 지나면 먼저 오는 쪽에 묶어서 POST /api/events 로 보낸다. 이탈 시점에는 sendBeacon 으로 잔여 버퍼를 flush 한다.',
      'logger.ts · 배치 20건 / 주기 5초 / 요청 상한 100건', 'done', '구현 완료'],
    ['3', 'Collector · Kafka',
      '수집 서버가 배치를 검증하고 봉투에 서버 메타(received_at·source·request_id·event_index)를 붙여 Kafka 로 발행한다. 과부하 시 ack 기반 백프레셔로 거절한다.',
      'Spring Boot Collector · Kafka activity-events', 'done', '구현 완료'],
    ['4', 'Spark 정제 · 집계',
      'Raw Event 를 Parquet 로 적재하고, 계약 위반 row 를 격리한 뒤 세션·상품·고객군 단위로 집계한다.',
      'raw_sink · clean_events · derive_facts · build_marts', 'partial', 'Job 작성 · 연결 검증 중'],
    ['5', 'Mart',
      '집계 결과를 Dashboard 가 바로 질의할 수 있는 형태로 적재한다.',
      'DW 스키마 정의 완료 · 집계 API 미연결', 'partial', '스키마 확정 · 적재 전'],
    ['6', 'B2B Dashboard (FE)',
      '기업 사용자가 보는 화면. Overview · 고객군 · 상품 · 행동 · 리뷰 · 성분 · 콘텐츠 7개 화면이 있다. '
      + '다만 파이프라인이 아직 데이터를 흘리기 전이라, 리뷰·성분은 실측값이고 행동 지표는 '
      + '시드 고정 모의값이다. 화면이 배지로 둘을 구분해 보여준다.',
      'dashboard.html · 화면 7개 · 집계 API 붙으면 metrics.ts 만 교체', 'partial', '화면 구현 · 데이터 대기'],
  ];

  h += `<div class="flow">`;
  for (const [n, title, what, how, state, label] of steps) {
    h += `<div class="step s-${state}">`
       + `<div class="stepn">${n}</div>`
       + `<div class="stepb"><div class="steph">${title}`
       + `<span class="badge b-${state}">${label}</span></div>`
       + `<p>${what}</p><p class="how">${how}</p></div></div>`;
  }
  h += `</div>`;

  h += `<h2 id="fl-who">트래픽 생성 주체는 둘이다</h2>`;
  h += `<p>실사용자가 없으므로 가상 소비자가 트래픽을 만든다. 두 경로는 `
     + `<strong>Event 를 누가 생성하느냐</strong>가 근본적으로 다르고, `
     + `<code>properties.generator_type</code> 으로 구분한다.</p>`;
  h += `<div class="tw"><table><thead><tr><th></th>`
     + `<th>PC 9,900명 <code>python_batch</code></th>`
     + `<th>PA 100명 <code>agent_llm</code></th></tr></thead><tbody>`
     + `<tr><td>실행 도구</td><td><code>gen_behavior_logs.py</code></td>`
     + `<td><code>agent_runner.py</code></td></tr>`
     + `<tr><td>행동 결정</td><td>확률 상태머신</td><td>LLM 이 화면을 읽고 판단</td></tr>`
     + `<tr><td>FE 화면 경유</td><td>경유하지 않음</td>`
     + `<td>Playwright 로 실제 DOM 조작</td></tr>`
     + `<tr><td>Event 생성 주체</td><td>스크립트가 직접 합성</td>`
     + `<td><strong>프론트 <code>log.ts</code></strong></td></tr>`
     + `<tr><td>검증 목적</td><td><strong>규모</strong> — Kafka·Spark TPS</td>`
     + `<td><strong>계약 정합성</strong> — 화면·Event·수집 API E2E</td></tr>`
     + `<tr><td>비용</td><td>없음</td><td>LLM 호출 크레딧</td></tr>`
     + `</tbody></table></div>`;
  h += `<p class="note">PA 는 합성 로그 대상에서 제외한다. 1인당 약 590건이 미리 쌓이면 `
     + `사용자가 직접 10회 클릭해도 벡터가 1.7% 만 움직여 `
     + `"행동에 따라 추천이 바뀐다" 를 시연할 수 없다. 부하 손실은 590만 건 중 1% 라 무시할 수준이다.</p>`;

  h += `<h2 id="fl-scale">처리 규모</h2>`;
  h += `<p>실측 기준 방문 1회당 Event 100~160건이 발생한다. 방문당 150건 · 90초면 `
     + `1인당 1.7 event/s 다.</p>`;
  h += `<div class="tw"><table><thead><tr><th>동시 사용자</th><th>Event TPS</th>`
     + `<th>요청/초</th></tr></thead><tbody>`
     + `<tr><td>100</td><td>170</td><td>20</td></tr>`
     + `<tr><td>1,000</td><td>1,700</td><td>200</td></tr>`
     + `<tr><td>10,000</td><td><strong>17,000</strong></td><td><strong>2,000</strong></td></tr>`
     + `</tbody></table></div>`;
  h += `<p class="note">부하 생성기는 브라우저가 아니라 이탈 위험이 없으므로 배치를 `
     + `500~2,000건으로 키운다. Event TPS 는 유지하면서 HTTP 요청 수만 줄어든다. `
     + `재시도·크기 상한 등 상세 규칙은 「로그 전송 주기 계약」에 있다.</p>`;
  return h;
}

// tier 'brief' = 발표에 들어가는 내용. tier 'deep' = 파트 내부 상세.
const GROUPS = [
  {
    id: 'brief', tier: 'brief', step: '1',
    role: '읽는 문서',
    name: '요약',
    note: '이 두 장이면 발표 내용은 다 들어 있습니다',
    docs: [
      { key: 'events', t: '이벤트 35종과 가중치', d: '무엇을 수집하고 각각 몇 점인가', gen: buildEvents },
      { key: 'flow', t: 'Event 수집 파이프라인', d: '화면 → 수집 → 분석 → Dashboard · 진행 상황', gen: buildFlow },
    ],
  },
  {
    id: 'basis', tier: 'basis', step: '2',
    role: '위 요약의 근거',
    name: '왜 그렇게 정했나',
    note: '"이 숫자 왜 이래요?" 라는 질문의 답이 여기 있습니다',
    docs: [
      { f: 'docs/analytics/behavior-log-design.md', t: '행동 로그 설계',
        d: '화면 어느 지점에서 왜 그 Event 를 남기는가' },
      { f: 'docs/analytics/marketing-signal-research.md', t: '마케팅 시그널 조사',
        d: '가중치를 그렇게 매긴 외부 사례·근거' },
    ],
  },
  {
    id: 'deep', tier: 'deep', step: '3',
    role: '근거의 원문',
    name: '데이터 · 백엔드 파트 계약',
    note: '구현할 때 보는 원문입니다. PM 이 다 읽을 필요는 없습니다',
    docs: [
      { f: 'contracts/event-schema.json', t: 'Raw Event JSON Schema', d: '검증기가 돌리는 단일 출처', json: true },
      { f: 'docs/analytics/event-taxonomy-trigger-schema.md', t: 'Event Taxonomy · Trigger', d: '발화 시점과 필수 property 전문' },
      { f: 'docs/analytics/event-contract-summary.md', t: 'Event 계약 요약', d: '타 파트용 축약본' },
      { f: 'docs/analytics/log-transport-contract.md', t: '로그 전송 주기 계약', d: '배치 · 재시도 · synthetic 표시' },
      { f: 'docs/analytics/processed-schema.md', t: 'Processed 스키마', d: 'Spark 정제 단계 컬럼' },
      { f: 'docs/analytics/dw-schema.md', t: 'DW 스키마', d: 'Mart 와 KPI 산식' },
    ],
  },
];




let nav = '', body = '', n = 0;
for (const g of GROUPS) {
  nav += `<div class="navgroup t-${g.tier}">`
       + `<div class="navhead"><span class="stepno n-${g.id}">${g.step}</span>`
       + `<span class="nh-t">${g.name}</span>`
       + `<span class="nh-r">${g.role}</span>`
       + `<span class="navnote">${g.note}</span></div>`;

  for (const d of g.docs) {
    const key = 'doc' + (n++);
    let html, toc = [], meta;

    if (d.gen) {
      html = d.gen();
      toc = [];
      meta = '이 페이지에서 만든 요약';
    } else {
      const raw = fs.readFileSync(path.join(ROOT, d.f), 'utf8');
      if (d.json) {
        html = `<h1>${escS(d.t)}</h1><p>${escS(d.d)}.</p>`
             + `<pre class="code" data-lang="json"><code>${escS(raw)}</code></pre>`;
      } else {
        const r = render(raw);
        html = r.html;
        toc = r.toc.filter(x => x.lv <= 3);
      }
      meta = `${d.f} · ${(Buffer.byteLength(raw, 'utf8') / 1024).toFixed(1)} KB`;
    }

    nav += `<button class="navitem" data-doc="${key}">`
         + `<span class="ni-t">${escS(d.t)}</span>`
         + `<span class="ni-d">${escS(d.d)}</span></button>`;

    const tocHtml = toc.length
      ? `<nav class="toc" aria-label="문서 목차"><div class="toclabel">이 문서 안에서</div>`
        + toc.map(x => `<a class="tl${x.lv}" href="#${x.id}">${escS(x.txt)}</a>`).join('')
        + `</nav>`
      : '';

    body += `<article class="doc" id="${key}" data-tier="${g.tier}" hidden>`
          + `<header class="dochead"><div class="eyebrow">`
          + `<span class="stepno n-${g.id}">${g.step}</span>`
          + `<span>${escS(g.name)}</span><span class="eb-r">${escS(g.role)}</span></div>`
          + `<h1 class="doctitle">${escS(d.t)}</h1><p class="docsub">${escS(d.d)}</p>`
          + `<p class="docpath"><code>${escS(meta)}</code></p></header>`
          + tocHtml
          + `<div class="prose">${html}</div></article>`;
  }
  nav += '</div>';
}





const head = `<title>A306 행동 기록 안내서</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Serif:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root{
  --ground:#fbfbfd; --panel:#f2f3f7; --raise:#ffffff;
  --ink:#191d27; --body:#2b313d; --muted:#606979; --faint:#8b93a2;
  --rule:#e0e3ec; --rule-soft:#eaecf3;
  --accent:#1f6b66; --accent-ink:#12514d;
  --g-brief:#1f6b66; --g-basis:#8a5a2b; --g-deep:#5a6478;
  --brief-bg:#e8f2f0; --brief-bd:#bcdcd7; --brief-hi:#ffffff;
  --basis-bg:#f6eee3; --basis-bd:#e2d0b8;
  --wt3:#1f6b66; --wt2:#3f7f6b; --wt1:#7d8a7e; --wt0:#9aa3ad;
  --ok:#2f7a55; --part:#9a6a1f; --todo:#8b93a2;
  --code-bg:#f4f5f9; --code-ink:#26303f;
  --shadow:0 1px 2px rgba(24,30,44,.05),0 8px 24px -12px rgba(24,30,44,.16);
  --sans:"IBM Plex Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;
  --serif:"IBM Plex Serif","Nanum Myeongjo",Georgia,serif;
  --mono:"IBM Plex Mono",ui-monospace,"Cascadia Mono",Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#11141b; --panel:#171b24; --raise:#1b202a;
    --ink:#eef1f6; --body:#ccd3de; --muted:#98a1b1; --faint:#6f7889;
    --rule:#282f3c; --rule-soft:#212734;
    --accent:#5fbcb2; --accent-ink:#8fd6ce;
    --g-brief:#5fbcb2; --g-basis:#c99a5e; --g-deep:#8b95a8;
    --brief-bg:#16302e; --brief-bd:#24544e; --brief-hi:#1b232b;
    --basis-bg:#2b2418; --basis-bd:#4a3c24;
    --wt3:#5fbcb2; --wt2:#54a394; --wt1:#8d9a92; --wt0:#6f7889;
    --ok:#5fb98a; --part:#d0a352; --todo:#6f7889;
    --code-bg:#161b23; --code-ink:#c8d2e0;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -12px rgba(0,0,0,.6);
  }
}
:root[data-theme="dark"]{
  --ground:#11141b; --panel:#171b24; --raise:#1b202a;
  --ink:#eef1f6; --body:#ccd3de; --muted:#98a1b1; --faint:#6f7889;
  --rule:#282f3c; --rule-soft:#212734;
  --accent:#5fbcb2; --accent-ink:#8fd6ce;
  --g-brief:#5fbcb2; --g-basis:#c99a5e; --g-deep:#8b95a8;
    --brief-bg:#16302e; --brief-bd:#24544e; --brief-hi:#1b232b;
    --basis-bg:#2b2418; --basis-bd:#4a3c24;
    --wt3:#5fbcb2; --wt2:#54a394; --wt1:#8d9a92; --wt0:#6f7889;
    --ok:#5fb98a; --part:#d0a352; --todo:#6f7889;
  --code-bg:#161b23; --code-ink:#c8d2e0;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -12px rgba(0,0,0,.6);
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--body);font-family:var(--sans);
  font-size:15px;line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{display:grid;grid-template-columns:298px minmax(0,1fr);align-items:start;
  max-width:1360px;margin:0 auto}

.side{position:sticky;top:0;height:100vh;overflow-y:auto;padding:26px 16px 40px;
  border-right:1px solid var(--rule);background:var(--panel);
  display:flex;flex-direction:column;gap:30px}
.brand{display:flex;flex-direction:column;gap:5px}
.brand b{font-size:15px;font-weight:600;color:var(--ink);letter-spacing:-.01em}
.brand span{font-size:11.5px;color:var(--faint)}
/* 그룹은 <nav> 안에 들어 있다. .side 의 gap 은 여기까지 오지 않는다 */
.side nav{display:flex;flex-direction:column;gap:30px}
.navgroup{display:flex;flex-direction:column;gap:6px}
.navhead{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap;font-family:var(--sans);
  padding:0 2px 11px}
.stepno{flex:none;width:17px;height:17px;border-radius:50%;display:inline-flex;
  align-items:center;justify-content:center;font-size:10.5px;font-weight:600;
  color:#fff;align-self:center}
.n-brief{background:var(--g-brief)} .n-basis{background:var(--g-basis)}
.n-deep{background:var(--g-deep)}
.nh-t{font-size:13px;font-weight:600;color:var(--ink)}
.nh-r{font-size:11px;color:var(--faint);font-weight:400}
.nh-r::before{content:"— "}
.navnote{flex:1 0 100%;padding-left:24px;font-size:11.5px;color:var(--muted);
  line-height:1.45;font-weight:400;margin-top:3px}

/* 아래 단계일수록 들여쓰고 세로선으로 묶어, 무엇이 무엇을 받치는지 보이게 한다 */
.navgroup{position:relative}
.t-basis .navitem,.t-deep .navitem{margin-left:16px}
.t-basis::before,.t-deep::before{content:"";position:absolute;left:8px;top:34px;bottom:6px;
  width:1px;background:var(--rule)}
.dot{width:7px;height:7px;border-radius:50%;flex:none}
.d-brief{background:var(--g-brief)}
.d-basis{background:var(--g-basis)}
.d-deep{background:var(--g-deep)}
.navitem{display:flex;flex-direction:column;gap:2px;width:100%;text-align:left;background:none;
  border:0;border-radius:7px;padding:8px 10px;cursor:pointer;font-family:inherit;color:var(--body);
  transition:background .12s}
.navitem:hover{background:var(--rule-soft)}
.navitem:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.navitem[aria-current="true"]{background:var(--raise);box-shadow:var(--shadow)}
.navitem[aria-current="true"] .ni-t{color:var(--accent-ink);font-weight:600}
.ni-t{font-size:13.5px;font-weight:500;color:var(--ink);line-height:1.35}
.ni-d{font-size:11.5px;color:var(--faint);line-height:1.4}

/* 계층별 버튼 배경. 발표용은 채워서 눈에 먼저 들어오게 한다 */
.t-brief .navitem{background:var(--brief-bg);border:1px solid var(--brief-bd)}
.t-brief .navitem:hover{background:var(--brief-hi)}
.t-brief .navitem[aria-current="true"]{background:var(--brief-hi);border-color:var(--accent)}
.t-brief .ni-t{color:var(--accent-ink);font-weight:600}
.t-brief .ni-d{color:var(--muted)}
.t-basis .navitem{background:var(--basis-bg);border:1px solid var(--basis-bd)}
.t-basis .navitem:hover{filter:brightness(1.03)}
.t-basis .navitem[aria-current="true"]{border-color:var(--g-basis)}
.t-deep .navitem{background:none;border:1px solid var(--rule-soft);padding:7px 10px}
.t-deep .ni-t{font-weight:500;font-size:13px;color:var(--muted)}
.t-deep .ni-d{font-size:11px}
.t-deep .navitem[aria-current="true"]{background:var(--raise);border-color:var(--rule)}

main{padding:44px 52px 120px;min-width:0}
.dochead{padding-bottom:22px;border-bottom:1px solid var(--rule);margin-bottom:26px}
.eyebrow{display:flex;align-items:center;gap:8px;font-size:12.5px;font-weight:600;
  color:var(--ink);margin-bottom:10px}
.eb-r{font-weight:400;color:var(--faint);font-size:11.5px}
.eb-r::before{content:"— "}
.doctitle{font-size:31px;line-height:1.2;font-weight:600;color:var(--ink);margin:0 0 8px;
  letter-spacing:-.02em;text-wrap:balance}
.docsub{margin:0 0 12px;color:var(--muted);font-size:14.5px}
.docpath{margin:0;font-size:11.5px;color:var(--faint)}
.docpath code{font-family:var(--mono);background:none;border:0;padding:0;
  color:var(--faint);font-size:11px;white-space:normal;overflow-wrap:anywhere}
.docpath code:lang(ko){font-family:var(--sans)}

.toc{display:flex;flex-direction:column;gap:1px;margin-bottom:30px;padding:14px 16px;
  background:var(--panel);border:1px solid var(--rule-soft);border-radius:9px;max-width:68ch}
.toclabel{font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--faint);margin-bottom:6px}
.toc a{color:var(--muted);text-decoration:none;font-size:12.5px;padding:2.5px 0;line-height:1.4}
.toc a:hover{color:var(--accent-ink)}
.toc a:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.toc .tl1{font-weight:600;color:var(--ink)}
.toc .tl3{padding-left:14px;font-size:12px;color:var(--faint)}

.prose{max-width:68ch;font-family:var(--serif);font-size:15.5px;line-height:1.75;color:var(--body)}
.prose h1,.prose h2,.prose h3,.prose h4,.prose h5,.prose h6{font-family:var(--sans);color:var(--ink);
  letter-spacing:-.012em;text-wrap:balance;scroll-margin-top:20px}
.prose h1{font-size:25px;font-weight:600;margin:44px 0 14px;line-height:1.25}
.prose h2{font-size:20px;font-weight:600;margin:40px 0 12px;padding-top:18px;
  border-top:1px solid var(--rule-soft);line-height:1.3}
.prose h3{font-size:16.5px;font-weight:600;margin:30px 0 9px}
.prose h4{font-size:14.5px;font-weight:600;margin:24px 0 7px;color:var(--muted)}
.prose > h1:first-child,.prose > h2:first-child{margin-top:0;border-top:0;padding-top:0}
.prose p{margin:0 0 15px}
.prose ul,.prose ol{margin:0 0 16px;padding-left:22px;display:flex;flex-direction:column;gap:5px}
.prose li{padding-left:2px}
.prose li > ul,.prose li > ol{margin:6px 0 0}
.prose a{color:var(--accent-ink);text-decoration:underline;text-underline-offset:2px}
.prose strong{font-weight:600;color:var(--ink)}
.prose hr{border:0;border-top:1px solid var(--rule);margin:34px 0}
.prose blockquote{margin:0 0 18px;padding:2px 0 2px 18px;border-left:2px solid var(--accent);
  color:var(--muted);font-style:italic}
.prose blockquote p:last-child{margin-bottom:0}
.prose code{font-family:var(--mono);font-size:.855em;background:var(--code-bg);color:var(--code-ink);
  padding:1.5px 5px;border-radius:4px;border:1px solid var(--rule-soft);
  overflow-wrap:anywhere}
.prose pre.code{background:var(--code-bg);border:1px solid var(--rule-soft);border-radius:9px;
  padding:15px 17px;overflow-x:auto;margin:0 0 18px;position:relative}
.prose pre.code code{background:none;border:0;padding:0;white-space:pre;font-size:12.6px;
  line-height:1.6;color:var(--code-ink)}
.prose pre.code[data-lang]::before{content:attr(data-lang);position:absolute;top:8px;right:12px;
  font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}

/* 요약 문서 전용 */
.prose .lead{font-size:17px;line-height:1.7;color:var(--ink)}
.prose .note{font-size:14px;color:var(--muted);background:var(--panel);
  border-left:2px solid var(--rule);padding:11px 15px;border-radius:0 7px 7px 0}
.prose .cnt{font-family:var(--mono);font-size:11px;font-weight:500;color:var(--faint);
  margin-left:9px;letter-spacing:.06em;text-transform:uppercase}
.kpirow{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:10px;
  margin:0 0 24px}
.kpi{background:var(--panel);border:1px solid var(--rule-soft);border-radius:9px;
  padding:13px 15px;display:flex;flex-direction:column;gap:2px}
.kpi b{font-family:var(--sans);font-size:25px;font-weight:600;color:var(--accent-ink);
  line-height:1.1;font-variant-numeric:tabular-nums}
.kpi span{font-size:11.5px;color:var(--muted);line-height:1.35}
.wt{display:inline-block;min-width:34px;text-align:center;font-family:var(--mono);
  font-size:12px;font-weight:600;padding:2px 7px;border-radius:5px;
  color:#fff;font-variant-numeric:tabular-nums}
.wt.w3{background:var(--wt3)} .wt.w2{background:var(--wt2)}
.wt.w1{background:var(--wt1)} .wt.w0{background:var(--wt0);opacity:.65}
.tw td.dim{color:var(--muted);font-size:12.5px}

/* 흐름 카드 */
.flow{display:flex;flex-direction:column;gap:9px;margin:0 0 24px}
.step{display:flex;gap:13px;background:var(--raise);border:1px solid var(--rule);
  border-radius:10px;padding:14px 16px}
.step.s-done{border-left:3px solid var(--ok)}
.step.s-partial{border-left:3px solid var(--part)}
.step.s-todo{border-left:3px solid var(--todo)}
.stepn{font-family:var(--mono);font-size:13px;font-weight:600;color:var(--faint);
  flex:none;width:18px;padding-top:2px}
.stepb{min-width:0;display:flex;flex-direction:column;gap:5px}
.steph{font-family:var(--sans);font-size:15.5px;font-weight:600;color:var(--ink);
  display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.stepb p{margin:0;font-size:14.5px;line-height:1.6}
.stepb p.how{font-family:var(--mono);font-size:11.5px;color:var(--faint);line-height:1.5}
.badge{font-family:var(--sans);font-size:10.5px;font-weight:500;padding:2px 8px;
  border-radius:20px;letter-spacing:.02em}
.badge.b-done{background:var(--ok);color:#fff}
.badge.b-partial{background:var(--part);color:#fff}
.badge.b-todo{background:var(--todo);color:#fff}

.tw{overflow-x:auto;margin:0 0 20px;border:1px solid var(--rule);border-radius:9px;
  background:var(--raise);max-width:min(78vw,980px)}
.tw table{border-collapse:collapse;width:100%;font-family:var(--sans);font-size:13px;
  font-variant-numeric:tabular-nums}
.tw th,.tw td{text-align:left;padding:9px 13px;border-bottom:1px solid var(--rule-soft);
  vertical-align:top;line-height:1.55}
.tw th{background:var(--panel);color:var(--ink);font-weight:600;font-size:11.5px;
  letter-spacing:.03em;white-space:nowrap}
.tw tr:last-child td{border-bottom:0}
.tw code{white-space:nowrap;font-size:.86em}

@media (max-width:960px){
  .wrap{grid-template-columns:1fr}
  .side{position:static;height:auto;max-height:44vh;border-right:0;
    border-bottom:1px solid var(--rule)}
  main{padding:30px 22px 90px}
  .tw{max-width:100%}
}
@media (prefers-reduced-motion:reduce){*{transition:none !important;scroll-behavior:auto !important}}
</style>`;

const html = head + `
<div class="wrap">
  <aside class="side">
    <div class="brand"><b>행동 기록 안내서</b><span>S15P21A306 · 이벤트와 점수</span></div>
    <nav aria-label="문서 목록">` + nav + `</nav>
  </aside>
  <main id="main">` + body + `</main>
</div>
<script>
(function () {
  var items = [].slice.call(document.querySelectorAll('.navitem'));
  var docs = [].slice.call(document.querySelectorAll('.doc'));
  function show(key, push) {
    docs.forEach(function (d) { d.hidden = d.id !== key; });
    items.forEach(function (b) { b.setAttribute('aria-current', String(b.dataset.doc === key)); });
    if (push) {
      try { history.replaceState(null, '', '#' + key); } catch (e) {}
      window.scrollTo(0, 0);
    }
  }
  items.forEach(function (b) {
    b.addEventListener('click', function () { show(b.dataset.doc, true); });
  });
  var start = (location.hash || '').replace('#', '');
  var el = start ? document.getElementById(start) : null;
  show(el && el.classList.contains('doc') ? start : 'doc0', false);
})();
</script>`;



const LF = String.fromCharCode(10);
const HEAD_OPEN = ['<!doctype html>', '<html lang="ko">', '<head>',
  '<meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">', ''].join(LF);
const BODY_OPEN = ['</head>', '<body>', '<div class="wrap">'].join(LF);
const TAIL = ['', '</body>', '</html>', ''].join(LF);

const doc = HEAD_OPEN + html.replace('<div class="wrap">', BODY_OPEN) + TAIL;
fs.writeFileSync(OUT, doc, 'utf8');
console.log('생성', path.relative(ROOT, OUT), (Buffer.byteLength(doc, 'utf8') / 1024).toFixed(0) + ' KB');