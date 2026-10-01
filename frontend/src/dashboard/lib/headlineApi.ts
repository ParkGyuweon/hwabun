/**
 * 대시보드 한 마디 · `POST /api/headline` (batch/serving/recommend_server.py, 8300).
 *
 * 계약: contracts/headline-api-spec.md. 처방(`/api/prescription`)과 자리가 다르다 — 처방은 "이번 주에 뭘 고칠까"
 * (지시문), 한 마디는 "지금 무슨 일이 일어나고 있나" (서술문). 이 파일은 서술문 쪽만 다룬다.
 *
 * 역할 분담(계약 §2). 숫자 계산·표기와 비교 판단은 **프론트**가 한다. 화면에 그린 문자열을 그대로 `facts` 에,
 * "늘었습니다/줄었습니다" 는 완성 문장으로 `comparisons` 에 넣는다. 서버는 거기 있는 숫자와 말로만 문장을 쓰고,
 * 없는 숫자·없는 비교·크기 부사("크게"·"훨씬")는 거부해 규칙 문장으로 바꾼다.
 *
 * 2026-09-21 결정 (규원님 09-20 전달 문서의 "확인 부탁" 네 가지 중 프론트 몫).
 *   - 붙이는 화면: **개요(`overview`) 하나.** 사장님이 처음 여는 화면이고 여기 숫자가 다른 화면의 요약이다.
 *     다른 화면은 이미 화면마다 결론 문장(insight.ts)이 있어 한 마디가 겹친다.
 *   - 섹션: traffic(찾아온 사람) · cart(담기) · repurchase(재구매) · orders(주문·매출). 값이 없는 섹션은 빼고 보낸다.
 *     계약 한도 8개 안이다.
 *   - origin 이 rule·mixed 면 그 줄에 옅은 "값 그대로" 배지를 단다. 요약처럼 읽히면 안 되는 나열이라는 표시다.
 *   - 마트가 실측일 때만 부른다. 모의 숫자를 LLM 에 보내 문장을 만들면 사장님이 진짜로 읽는다.
 *
 * Vite 프록시가 `/api/headline` 을 8300 으로 보낸다 (vite.config.ts). 배포본은 nginx 정확 일치 블록(계약 §7).
 * 같은 입력은 이 탭에서 한 번만 부른다 (서버도 input_hash 로 캐시하지만 왕복을 아낀다).
 */
import { useEffect, useMemo, useState } from 'react';
import type { SellerPulse } from '../../lib/shopApi';
import type { BehaviorMetrics, Overview } from './behavior';
import { fmt } from './metrics';

/** 계약 §3 입력 */
export interface HeadlineRequest {
  brand: { name: string; product_count: number; functional_certified?: boolean };
  screen: { id: string; label_ko: string; period_text: string };
  sections: Array<{
    id: string;
    label_ko: string;
    facts: Array<{ label_ko: string; value_text: string }>;
    comparisons: string[];
    thin: boolean;
  }>;
}

export type HeadlineOrigin = 'llm' | 'mixed' | 'rule' | 'none';

/** 계약 §4 응답 */
export interface HeadlineEnvelope {
  screen: string;
  brand: string;
  headline: string | null;
  /** 화면 전체 줄의 출처. `origin: "mixed"` 일 때 본다. 없으면 봉투의 origin 과 같다 */
  headline_origin?: 'llm' | 'rule';
  sections: Array<{ id: string; line: string; origin?: 'llm' | 'rule' }>;
  origin: HeadlineOrigin;
  rejected_by: string[];
  needs_evidence: string[];
  model?: string;
  cached?: boolean;
}

/** 화면이 이미 흐리게 그리는 기준. 상세 조회가 이보다 적으면 결론 대신 "이르다" 쪽으로 간다 */
const THIN_DETAIL_VIEWS = 200;

/** 받침이 있으면 앞, 없으면 뒤. 한글이 아니면(숫자·%) 읽는 소리로 — "%" 는 "퍼센트" 라 받침 없음 */
function josa(word: string, withBatchim: string, without: string, rieulAsNone = false): string {
  const ch = word.trim().slice(-1);
  if (ch === '%') return without;
  if (ch >= '가' && ch <= '힣') {
    const jong = (ch.charCodeAt(0) - 0xac00) % 28;
    if (jong === 0) return without;
    // "으로/로" 는 ㄹ 받침 뒤에서 "로" 다 (1,170일로)
    if (rieulAsNone && jong === 8) return without;
    return withBatchim;
  }
  return withBatchim;
}

/**
 * 변화의 크기를 말로. **서버는 비교 문장에 있는 말만 쓰게 한다** — "크게"·"소폭" 이 여기 없으면 AI 가 그 말을 쓴 줄은
 * unsupported_comparison 으로 걸려 숫자 나열이 된다 (2026-10-01 실측: "크게 늘었습니다" 가 걸렸다). 그래서 실제 폭을
 * 재서 맞는 말을 미리 넣어 준다. 지어낸 크기가 아니라 계산한 크기다.
 *   - 횟수·건수: 직전 대비 30% 이상 "크게", 10% 미만 "소폭"
 *   - 비율: 5%p 이상 "크게", 1%p 미만 "소폭"
 */
function magnitude(prev: number, cur: number, kind: 'count' | 'rate'): string {
  const diff = Math.abs(cur - prev);
  if (kind === 'rate') {
    const pts = diff * 100;
    if (pts >= 5) return '크게 ';
    if (pts < 1) return '소폭 ';
    return '';
  }
  if (prev <= 0) return '';
  const rel = diff / prev;
  if (rel >= 0.3) return '크게 ';
  if (rel < 0.1) return '소폭 ';
  return '';
}

/**
 * 두 값의 비교를 완성 문장으로. 서버는 이 문장 안의 말로만 변화를 말할 수 있다 (계약 §3).
 * 숫자 표기는 facts 와 글자까지 같아야 한다 — 같은 포매터를 쓴다.
 */
function compare(
  label: string,
  prevText: string,
  curText: string,
  prev: number,
  cur: number,
  periodText: string,
  up = '늘었습니다',
  down = '줄었습니다',
  kind: 'count' | 'rate' = 'count',
): string {
  const subj = `${label}${josa(label, '이', '가')}`;
  const same = Math.abs(cur - prev) < 1e-9 || prevText === curText;
  if (same) return `${subj} 직전 ${periodText}${josa(periodText, '과', '와')} 같은 ${curText}입니다.`;
  return `${subj} 직전 ${periodText} ${prevText}에서 ${curText}${josa(curText, '으로', '로', true)} ${magnitude(prev, cur, kind)}${cur > prev ? up : down}.`;
}

/**
 * 개요 화면의 입력. 값이 없는 섹션은 넣지 않는다 — `facts` 도 `comparisons` 도 비면 서버가 `empty_section` 으로 거부한다.
 * 마트가 실측이 아니면 null (부르지 않는다).
 */
export function buildOverviewHeadlineRequest(
  m: BehaviorMetrics,
  brand: { name: string; productCount: number },
  days: number,
  pulse: SellerPulse | null,
): HeadlineRequest | null {
  if (m.source.overview !== 'real' || !brand.name) return null;
  const o: Overview = m.overview;
  const p: Overview | null = m.previous;
  const periodText = `${days}일`;
  const thin = o.detailViews < THIN_DETAIL_VIEWS;
  const sections: HeadlineRequest['sections'] = [];

  // 찾아온 방문 — 방문 수(건)라 "사람" 이 아니다
  {
    const facts = [
      { label_ko: '방문', value_text: `${fmt.int(o.sessions)}건` },
      // 둘 다 방문 수가 아니라 횟수다 (product_view_count·add_to_cart_count). "방문" 으로 적으면 한 마디가 틀린 말을 한다
      { label_ko: '상세를 본 횟수', value_text: `${fmt.int(o.detailViews)}번` },
      { label_ko: '장바구니에 담은 횟수', value_text: `${fmt.int(o.addToCart)}번` },
    ];
    const comparisons: string[] = [];
    if (p) {
      comparisons.push(compare('상세를 본 횟수', `${fmt.int(p.detailViews)}번`, `${fmt.int(o.detailViews)}번`, p.detailViews, o.detailViews, periodText));
    }
    sections.push({ id: 'traffic', label_ko: '찾아온 방문', facts, comparisons, thin });
  }

  // 담기
  {
    const facts = [
      { label_ko: '상세에서 담기까지 간 비율', value_text: fmt.pct(o.cartRate) },
      { label_ko: '성분·리뷰를 확인한 비율', value_text: fmt.pct(o.infoRate) },
      { label_ko: '담았다 뺀 비율', value_text: fmt.pct(o.removalRate) },
    ];
    const comparisons: string[] = [];
    if (p) {
      comparisons.push(compare('상세에서 담기까지 간 비율', fmt.pct(p.cartRate), fmt.pct(o.cartRate), p.cartRate, o.cartRate, periodText, '올랐습니다', '내렸습니다', 'rate'));
      comparisons.push(compare('담았다 뺀 비율', fmt.pct(p.removalRate), fmt.pct(o.removalRate), p.removalRate, o.removalRate, periodText, '올랐습니다', '내렸습니다', 'rate'));
    }
    sections.push({ id: 'cart', label_ko: '담기', facts, comparisons, thin });
  }

  // 재구매. 마트가 있을 때만 (개요 화면과 같은 조건)
  const rb = m.repurchase?.brand;
  if (rb) {
    const facts = [
      { label_ko: '구매 고객', value_text: `${fmt.int(rb.buyerCount)}명` },
      { label_ko: '다시 산 고객', value_text: `${fmt.int(rb.repeatBuyerCount)}명` },
    ];
    if (rb.rate !== null) facts.push({ label_ko: '다시 산 고객 비율', value_text: fmt.pct(rb.rate) });
    if (rb.medianDays !== null) facts.push({ label_ko: '다시 사기까지 걸린 날', value_text: `${Math.round(rb.medianDays)}일` });
    sections.push({ id: 'repurchase', label_ko: '다시 산 고객', facts, comparisons: [], thin: rb.buyerCount < 10 });
  }

  // 주문·매출. 백엔드 실측이 있을 때만
  if (pulse) {
    sections.push({
      id: 'orders',
      label_ko: '주문·매출',
      facts: [
        { label_ko: '결제 완료 주문', value_text: `${fmt.int(pulse.orders)}건` },
        { label_ko: '매출', value_text: `${Math.round(pulse.revenue).toLocaleString('ko-KR')}원` },
        { label_ko: '판매 수량', value_text: `${fmt.int(pulse.units)}개` },
        { label_ko: '리뷰', value_text: `${fmt.int(pulse.reviews)}건` },
      ],
      comparisons: [],
      thin: pulse.orders < 10,
    });
  }

  // 넷이 전부 비면 서버가 no_section 으로 통째 거부한다 — 그때는 부르지 않는다 (규원님 09-21). 처방과 달리 최소 2개 조건은 없다
  if (sections.length === 0) return null;

  return {
    brand: { name: brand.name, product_count: brand.productCount },
    screen: { id: 'overview', label_ko: '한눈에 보기', period_text: `최근 ${periodText}` },
    sections,
  };
}

const inflight = new Map<string, Promise<HeadlineEnvelope | null>>();

/** AI 한 마디를 기다리는 최대 시간. 보통 1.5~3초, 처음 만드는 문장도 10초 안쪽이다 */
const HEADLINE_TIMEOUT_MS = 15_000;

/** 서버가 못 답하면 null. 계약상 503 은 없지만 경로가 없으면(404) 그냥 안 그린다 */
export function fetchHeadline(req: HeadlineRequest): Promise<HeadlineEnvelope | null> {
  const key = JSON.stringify(req);
  const hit = inflight.get(key);
  if (hit) return hit;
  const p = (async () => {
    // 답이 안 오면 "분석 중" 이 끝나지 않는다 — HEADLINE_TIMEOUT_MS 뒤 끊고 기본 문장으로 간다 (2026-10-01)
    const ctrl = new AbortController();
    const timer = window.setTimeout(() => ctrl.abort(), HEADLINE_TIMEOUT_MS);
    try {
      const res = await fetch('/api/headline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: key,
        signal: ctrl.signal,
      });
      if (!res.ok) return null;
      const body = (await res.json()) as HeadlineEnvelope;
      if (!body || !Array.isArray(body.sections) || typeof body.origin !== 'string') return null;
      return body;
    } catch {
      return null;
    } finally {
      window.clearTimeout(timer);
    }
  })();
  inflight.set(key, p);
  // 실패는 기억하지 않는다 — 기간을 바꿨다 돌아오는 등 다음에 같은 요청을 만들면 다시 묻는다
  void p.then((env) => {
    if (env === null) inflight.delete(key);
  });
  return p;
}

/** 요청이 null 이거나 아직 답이 없으면 null. 입력이 바뀌면(브랜드·기간·값) 다시 묻는다 */
export function useHeadline(req: HeadlineRequest | null): HeadlineEnvelope | null {
  const key = useMemo(() => (req ? JSON.stringify(req) : null), [req]);
  const [state, setState] = useState<{ key: string; env: HeadlineEnvelope | null } | null>(null);

  useEffect(() => {
    if (!req || !key) return;
    let alive = true;
    void fetchHeadline(req).then((env) => {
      if (alive) setState({ key, env });
    });
    return () => {
      alive = false;
    };
    // 내용이 같은 요청은 다시 부르지 않는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return state && state.key === key ? state.env : null;
}

/**
 * `useHeadline` 과 같지만 **기다리는 중**을 따로 알려 준다 — 개요가 자리를 미리 잡고 "분석 중" 을 띄우려면
 * "아직 답이 없다" 와 "못 받았다(null)" 를 갈라야 한다 (2026-10-01). 요청이 null 이면 기다릴 것이 없다.
 */
export function useHeadlineState(req: HeadlineRequest | null): { loading: boolean; env: HeadlineEnvelope | null } {
  const key = useMemo(() => (req ? JSON.stringify(req) : null), [req]);
  const [state, setState] = useState<{ key: string; env: HeadlineEnvelope | null } | null>(null);

  useEffect(() => {
    if (!req || !key) return;
    let alive = true;
    void fetchHeadline(req).then((env) => {
      if (alive) setState({ key, env });
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (!key) return { loading: false, env: null };
  return state && state.key === key ? { loading: false, env: state.env } : { loading: true, env: null };
}

/** 줄 하나의 출처. `mixed` 면 줄마다, 아니면 봉투 값을 따른다 */
export function lineOrigin(env: HeadlineEnvelope, line: { origin?: 'llm' | 'rule' }): 'llm' | 'rule' {
  if (env.origin === 'mixed') return line.origin ?? 'rule';
  return env.origin === 'llm' ? 'llm' : 'rule';
}

export function headlineOrigin(env: HeadlineEnvelope): 'llm' | 'rule' {
  if (env.origin === 'mixed') return env.headline_origin ?? 'rule';
  return env.origin === 'llm' ? 'llm' : 'rule';
}
