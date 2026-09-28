/**
 * 처방 문장 API 연결 · `POST /api/prescription` (batch/serving/recommend_server.py, 8300).
 *
 * 계약: contracts/prescription-api-spec.md · 규격 docs/dashboard/action-prescription-prompt.md v0.3.
 * 역할 분담(계약 §1): 판정(up·fix)과 옮길 위치는 **프론트**가 정해 입력에 넣고, 문장은 서버(LLM)가 쓴다.
 *
 * 순서
 *   1. 규칙 표(prescription.ts)로 먼저 그린다. 화면이 비는 순간이 없다
 *   2. 신호가 2개 이상 모이는 콘텍츠만 서버에 묻는다 (규격 §3 "신호 1개면 부르지 않는다")
 *   3. 서버가 처방을 주면 바꿔 끼운다. 거부(`rejected_by`)·오류·미기동이면 규칙 표 그대로
 *
 * Vite 프록시가 `/api/prescription` 을 8300 으로 보낸다. 없으면 8080 수집 서버로 가서 404 → 규칙 표.
 * 같은 입력은 이 탭에서 한 번만 부른다 (서버도 input_hash 로 캐시하지만 왕복을 아낀다).
 */
import { useEffect, useMemo, useState } from 'react';
import { labelKo } from '../../lib/formLabels';
import type { BehaviorMetrics } from './behavior';
import type { ContentAttention } from './metrics';
import { SKIN_TYPE_KO, fmt } from './metrics';
import { type Prescription, type PrescriptionEnvelope, buildPrescriptions, fromEnvelope, insertAfter } from './prescription';

export type Verb = 'up' | 'fix' | 'keep';

/** 규격 §3 입력 */
export interface PrescriptionRequest {
  brand: { name: string; product_count: number; functional_certified?: boolean };
  target: {
    content_kind: string;
    label_ko: string;
    verb: 'up' | 'fix';
    dwell_sec: number;
    view_rate_text: string;
    cart_lift_text: string;
    sample_size: number;
    position_in_page: number;
    total_blocks: number;
    insert_after?: string;
  };
  page_context: {
    blocks_in_order: Array<{ label_ko: string; view_rate_text: string; cart_lift_text: string }>;
    quick_exit_rate_text: string;
    brand_cart_rate_text: string;
  };
  cross_screen_signals: Array<{ from: string; signal: string; text: string; sample_size: number }>;
}

/** 처방 한 건의 출처. 화면 하단 문구에 쓴다 */
export interface PrescriptionResult {
  rx: Prescription | null;
  origin: 'llm' | 'rule' | 'none';
  needsEvidence: string[];
  model?: string;
}

const MIN_SIGNAL_N = 200;

/**
 * 교차 화면 신호. 규격 §3: `from` 은 여섯 화면 이름, `sample_size` ≥ 200 만, 문장은 완성형.
 * 표본은 그 신호가 나온 집계의 분모다. 브랜드 집계 신호는 상세 조회 세션을 쓴다.
 */
function crossSignals(m: BehaviorMetrics, target: ContentAttention): PrescriptionRequest['cross_screen_signals'] {
  const n = m.overview.sessions;
  const out: PrescriptionRequest['cross_screen_signals'] = [];

  const seg = m.segmentTopContent.find((s) => s.top === target.ko);
  if (seg) {
    out.push({
      from: '누가 사나',
      signal: 'segment_top_content',
      text: `${SKIN_TYPE_KO[seg.type]} 고객이 가장 오래 보는 글이 ${target.ko}입니다. 이 고객군 체류의 ${fmt.pct(seg.dwellShare)}입니다.`,
      sample_size: n,
    });
  }

  const drag = m.scrapedIngredients.slice(0, 3);
  if (drag.length === 3 && target.kind.startsWith('ingredient')) {
    out.push({
      from: '고객이 찾는 성분',
      signal: 'dragged_ingredients_top3',
      // 점수(direct_match_score)를 "N회" 로 적으면 틀린 숫자가 된다. 건수는 관련 행동 수로 적는다
      text: `고객이 이름을 가장 많이 긁거나 복사한 성분은 ${drag.map((d) => `${labelKo(d.name)}(관련 행동 ${fmt.int(d.events)}번)`).join(', ')}입니다.`,
      sample_size: drag.reduce((s, d) => s + d.events, 0),
    });
  }

  const backtrack = m.frictionByLocation.find((f) => f.where === '성분 목록' && f.event === 'scroll_backtrack');
  if (backtrack && target.kind.startsWith('ingredient')) {
    out.push({
      from: '막히는 곳',
      signal: 'scroll_backtrack_by_location',
      text: `성분 목록 구간에서 위로 다시 올려 읽은 기록이 ${fmt.int(backtrack.count)}건입니다.`,
      sample_size: n,
    });
  }

  const dead = m.frictionByLocation.find((f) => f.where === '상품 이미지' && f.event === 'dead_click');
  if (dead && target.kind === 'product_image') {
    out.push({
      from: '막히는 곳',
      signal: 'dead_click_by_location',
      text: `상품 이미지에서 눌러도 아무 일이 없었던 기록이 ${fmt.int(dead.count)}건입니다.`,
      sample_size: n,
    });
  }

  const behaviorFor: Record<string, string> = {
    ingredient_list: 'ingredient_view_mode_change',
    ingredient_callout: 'ingredient_view_mode_change',
    clinical_claim: 'ingredient_view_mode_change',
    user_review: 'review_filter_apply',
    review_stats: 'review_filter_apply',
    usage_guide: 'accordion_toggle',
    what_else: 'accordion_toggle',
  };
  const b = m.validationBehaviors.find((v) => v.event === behaviorFor[target.kind]);
  if (b) {
    out.push({
      from: '무엇을 보고 사나',
      signal: 'validation_behavior',
      text: `${b.ko} 방문의 담기율은 ${fmt.pct(b.cartRateWith)}, 안 한 방문은 ${fmt.pct(b.cartRateWithout)}입니다.`,
      sample_size: n,
    });
  }

  if (target.kind === 'what_else') {
    out.push({
      from: '막히는 곳',
      signal: 'quick_exit_rate',
      text: `상세페이지를 열고 3초 안에 나간 방문이 ${fmt.pct(m.quickExitRate)}입니다.`,
      sample_size: n,
    });
  }

  return out.filter((s) => s.sample_size >= MIN_SIGNAL_N).slice(0, 6);
}

/** 규격 §3 입력을 만든다. 신호가 2개 미만이면 null (부르지 않는다) */
export function buildPrescriptionRequest(
  m: BehaviorMetrics,
  target: ContentAttention,
  verb: 'up' | 'fix',
  brand: { name: string; productCount: number },
): PrescriptionRequest | null {
  const signals = crossSignals(m, target);
  if (signals.length < 2) return null;

  // 노출 순서 마트가 없어 담기율 내림차순을 순서로 쓴다 (prescription.ts insertAfter 와 같은 대체)
  const ordered = [...m.contentAttention].sort((a, b) => b.conversionLift - a.conversionLift);
  const position = ordered.findIndex((c) => c.kind === target.kind) + 1;
  const after = verb === 'up' ? insertAfter(target.kind, m.contentAttention) : null;

  return {
    brand: { name: brand.name, product_count: brand.productCount },
    target: {
      content_kind: target.kind,
      label_ko: target.ko,
      verb,
      dwell_sec: Math.round(target.avgDwellMs / 1000),
      view_rate_text: fmt.pct(target.viewRate),
      cart_lift_text: `${target.conversionLift.toFixed(1)}배`,
      sample_size: target.sampleSize,
      position_in_page: position,
      total_blocks: ordered.length,
      ...(verb === 'up' ? { insert_after: after ?? '맨 위' } : {}),
    },
    page_context: {
      blocks_in_order: ordered.map((c) => ({ label_ko: c.ko, view_rate_text: fmt.pct(c.viewRate), cart_lift_text: `${c.conversionLift.toFixed(1)}배` })),
      quick_exit_rate_text: fmt.pct(m.quickExitRate),
      brand_cart_rate_text: fmt.pct(m.overview.cartRate),
    },
    cross_screen_signals: signals,
  };
}

const inflight = new Map<string, Promise<PrescriptionEnvelope | null>>();

export function fetchPrescription(req: PrescriptionRequest): Promise<PrescriptionEnvelope | null> {
  const key = JSON.stringify(req);
  const hit = inflight.get(key);
  if (hit) return hit;
  const p = (async () => {
    try {
      const res = await fetch('/api/prescription', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: key,
      });
      if (!res.ok) return null;
      const body = (await res.json()) as PrescriptionEnvelope;
      if (!body || !Array.isArray(body.rejected_by)) return null;
      return body;
    } catch {
      return null;
    }
  })();
  inflight.set(key, p);
  return p;
}

/**
 * 콘텍츠별 처방. 처음 렌더는 규칙 표, 서버 응답이 오면 교체.
 * `targets` 는 up·fix 판정이 난 콘텐츠만. keep 은 처방을 만들지 않는다 (규격 §3).
 */
export function usePrescriptions(
  m: BehaviorMetrics,
  targets: Array<{ row: ContentAttention; verb: 'up' | 'fix' }>,
  brand: { name: string; productCount: number },
): Record<string, PrescriptionResult> {
  const rules = useMemo(() => buildPrescriptions(m), [m]);
  const [remote, setRemote] = useState<Record<string, PrescriptionEnvelope>>({});

  // 입력이 바뀌면(브랜드·기간·판정) 다시 묻는다. 서버는 input_hash 로 같은 입력을 캐시한다
  const requests = useMemo(
    () => targets.map((t) => ({ kind: t.row.kind, req: buildPrescriptionRequest(m, t.row, t.verb, brand) })).filter((x) => x.req !== null),
    [m, targets, brand],
  );
  const reqKey = useMemo(() => JSON.stringify(requests), [requests]);

  useEffect(() => {
    if (requests.length === 0) return;
    let alive = true;
    void Promise.all(
      requests.map(async ({ kind, req }) => {
        const env = req ? await fetchPrescription(req) : null;
        return [kind, env] as const;
      }),
    ).then((pairs) => {
      if (!alive) return;
      const next: Record<string, PrescriptionEnvelope> = {};
      for (const [kind, env] of pairs) if (env) next[kind] = env;
      setRemote(next);
    });
    return () => {
      alive = false;
    };
    // requests 의 내용이 같으면 다시 부르지 않는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reqKey]);

  return useMemo(() => {
    const out: Record<string, PrescriptionResult> = {};
    for (const t of targets) {
      const kind = t.row.kind;
      const env = remote[kind];
      const llm = env ? fromEnvelope(env) : null;
      if (llm) {
        out[kind] = { rx: llm, origin: 'llm', needsEvidence: env?.needs_evidence ?? [], model: env?.model };
      } else if (rules[kind]) {
        out[kind] = { rx: rules[kind], origin: 'rule', needsEvidence: [] };
      } else {
        out[kind] = { rx: null, origin: 'none', needsEvidence: [] };
      }
    }
    return out;
  }, [targets, remote, rules]);
}
