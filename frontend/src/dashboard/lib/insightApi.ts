/**
 * AI 고객 목소리 요약 · 읽기와 즉시 반영 (계약 contracts/feedback-insight-spec.md 초안 0.1).
 *
 *   GET  /api/seller/insights?brandId=&productId=      최근 요약 하나. 없으면 204
 *   POST /api/seller/insights/refresh?brandId=          다시 생성. 200 이면 완성본, 202 면 jobId 로 폴링, 409 면 거부
 *   GET  /api/seller/insights/refresh/{jobId}           running · done(+insight) · failed
 *
 * 서버가 아직 없으면(404·5xx·연결 실패) 'unavailable' 이다. 화면은 그때 "연결 전" 을 적고 버튼을 잠근다.
 * 프론트는 요약을 만들지 않는다 — 규칙 표 폴백도 없다. 원문 없이 만든 요약은 없는 사실이 된다.
 */
import { authFetch } from '../../lib/auth';
import type { RefreshJobState, RefreshResult, SellerInsight } from '../../types/insight';

export type InsightRead = { kind: 'ready'; insight: SellerInsight } | { kind: 'empty' } | { kind: 'unavailable' };

function asInsight(raw: unknown): SellerInsight | null {
  if (!raw || typeof raw !== 'object') return null;
  const j = raw as Record<string, unknown>;
  if (typeof j.generatedAt !== 'string' || !j.summary || typeof j.summary !== 'object') return null;
  const s = j.summary as Record<string, unknown>;
  const input = (j.inputCount ?? {}) as Record<string, unknown>;
  const list = <T>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
  return {
    brandId: String(j.brandId ?? ''),
    productId: j.productId ? String(j.productId) : null,
    generatedAt: j.generatedAt,
    source: j.source === 'manual' ? 'manual' : 'scheduled',
    inputCount: { feedback: Number(input.feedback ?? 0), review: Number(input.review ?? 0) },
    newSince: Number(j.newSince ?? 0),
    summary: {
      topComplaints: list<{ text: string; count: number; axisId?: string | null }>(s.topComplaints).slice(0, 3),
      preBuyDropReasons: list<{ text: string; count: number }>(s.preBuyDropReasons),
      priceMentionRate: typeof s.priceMentionRate === 'number' ? s.priceMentionRate : null,
      actions: list<string>(s.actions).slice(0, 3),
    },
    evidence: list<SellerInsight['evidence'][number]>(j.evidence),
    model: typeof j.model === 'string' ? j.model : null,
  };
}

export async function fetchSellerInsight(brandId: string, productId: string | null): Promise<InsightRead> {
  const q = new URLSearchParams({ brandId });
  if (productId) q.set('productId', productId);
  try {
    const res = await authFetch('SELLER', `/api/seller/insights?${q.toString()}`);
    if (res.status === 204) return { kind: 'empty' };
    if (!res.ok) return { kind: 'unavailable' };
    const text = await res.text();
    if (!text) return { kind: 'empty' };
    const insight = asInsight(JSON.parse(text));
    return insight ? { kind: 'ready', insight } : { kind: 'unavailable' };
  } catch {
    return { kind: 'unavailable' };
  }
}

export async function requestInsightRefresh(brandId: string, productId: string | null): Promise<RefreshResult> {
  const q = new URLSearchParams({ brandId });
  if (productId) q.set('productId', productId);
  try {
    const res = await authFetch('SELLER', `/api/seller/insights/refresh?${q.toString()}`, { method: 'POST' });
    if (res.status === 409 || res.status === 429) {
      const j = (await res.json().catch(() => ({}))) as { reason?: string; retryAfterSec?: number };
      const header = Number(res.headers.get('Retry-After'));
      return {
        kind: 'rejected',
        reason: j.reason ?? (res.status === 429 ? 'too_soon' : 'nothing_new'),
        retryAfterSec: Number.isFinite(j.retryAfterSec) ? Number(j.retryAfterSec) : Number.isFinite(header) && header > 0 ? header : null,
      };
    }
    if (res.status === 202) {
      const j = (await res.json()) as { jobId?: string };
      return j.jobId ? { kind: 'accepted', jobId: String(j.jobId) } : { kind: 'unavailable' };
    }
    if (!res.ok) return { kind: 'unavailable' };
    const insight = asInsight(await res.json());
    return insight ? { kind: 'done', insight } : { kind: 'unavailable' };
  } catch {
    return { kind: 'unavailable' };
  }
}

export async function fetchRefreshJob(
  jobId: string,
): Promise<{ state: RefreshJobState; insight: SellerInsight | null }> {
  try {
    const res = await authFetch('SELLER', `/api/seller/insights/refresh/${encodeURIComponent(jobId)}`);
    if (!res.ok) return { state: 'failed', insight: null };
    const j = (await res.json()) as { status?: string; insight?: unknown };
    if (j.status === 'done') return { state: 'done', insight: asInsight(j.insight) };
    if (j.status === 'failed') return { state: 'failed', insight: null };
    return { state: 'running', insight: null };
  } catch {
    return { state: 'failed', insight: null };
  }
}
