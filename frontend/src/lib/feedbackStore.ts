/**
 * 피드백 저장소 — 쇼핑몰(index.html)과 대시보드(dashboard.html)가 같은 origin 이라
 * localStorage 로 건너간다. 대시보드에서 반영 처리하면 쇼핑몰 탭이 storage 이벤트로
 * 새로고침 없이 따라온다 (storefront.ts 와 같은 방식).
 *
 * 두 층으로 나뉜다.
 *   시드   분류기(Jira 201·202)가 낸 30건. 파일이라 읽기 전용 → 상태·답글만 덧씌운다
 *   로컬   쇼핑몰에서 새로 쓴 글. 분류기가 없어서 분류 필드는 null 로 남는다
 *
 * 백엔드 Feedback API 가 생기면 이 파일의 함수 본문만 fetch 로 바뀐다.
 */
import seedJson from '../mocks/feedback.classified.json';
import { axisLabel } from '../types/feedback';
import type { Feedback, FeedbackStatus } from '../types/feedback';

export const FEEDBACK_KEY = 'hwabun.feedback.v2';

type SeedRow = Omit<Feedback, 'status' | 'reply' | 'replied_at'>;
type Override = Pick<Feedback, 'status' | 'reply' | 'replied_at'>;
interface Stored {
  /** 시드 행의 상태·답글. 키 = feedback_id */
  overrides: Record<string, Override>;
  /** 쇼핑몰에서 새로 쓴 글 (최신 먼저) */
  local: Feedback[];
}

const SEED: SeedRow[] = (seedJson as { rows: SeedRow[] }).rows;
const EMPTY: Stored = { overrides: {}, local: [] };

const listeners = new Set<() => void>();
let stored: Stored | null = null;
let snapshot: Feedback[] | null = null;

function readStored(): Stored {
  if (stored) return stored;
  try {
    const raw = window.localStorage.getItem(FEEDBACK_KEY);
    const parsed = raw ? (JSON.parse(raw) as Partial<Stored>) : null;
    stored = parsed && typeof parsed === 'object'
      ? { overrides: parsed.overrides ?? {}, local: Array.isArray(parsed.local) ? parsed.local : [] }
      : { ...EMPTY };
  } catch {
    stored = { ...EMPTY };
  }
  return stored;
}

function writeStored(next: Stored): void {
  stored = next;
  snapshot = null;
  try {
    window.localStorage.setItem(FEEDBACK_KEY, JSON.stringify(next));
  } catch {
    // 저장이 막힌 환경이면 메모리로만 산다
  }
  for (const l of listeners) l();
}

// 다른 탭(대시보드 ↔ 쇼핑몰)의 변경을 받는다
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key !== FEEDBACK_KEY) return;
    stored = null;
    snapshot = null;
    for (const l of listeners) l();
  });
}

export function subscribeFeedback(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** `useSyncExternalStore` 스냅샷. 같은 내용이면 같은 배열 참조를 돌려준다 */
export function feedbackSnapshot(): Feedback[] {
  if (snapshot) return snapshot;
  const s = readStored();
  const fresh: Override = { status: 'new', reply: null, replied_at: null };
  const seeded: Feedback[] = SEED.map((row) => ({ ...row, ...(s.overrides[row.feedback_id] ?? fresh) }));
  snapshot = [...s.local, ...seeded].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  return snapshot;
}

/** 쇼핑몰 "사장님께 의견 보내기". 분류는 소비자가 고르지 않는다 — 계약 §1 */
export function submitFeedback(input: {
  product_id: string;
  brand_name: string;
  user_id: string | null;
  /** 고객이 토글로 고른 축 (계약 0.2.0 §3 필수). 분류기는 이 축 안에서만 카테고리를 고른다 */
  axis_id: string;
  body: string;
}): Feedback {
  const item: Feedback = {
    feedback_id: `fb-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    user_id: input.user_id,
    product_id: input.product_id,
    body: input.body.trim(),
    created_at: new Date().toISOString(),
    axis_id: input.axis_id,
    axis: axisLabel(input.axis_id),
    labels: [],
    primary: null,
    off_axis_hint: null,
    category_id: null,
    category: null,
    classifier: null,
    vocab_version: null,
    classified_at: null,
    banned_terms: [],
    hidden_by_default: false,
    brand_name: input.brand_name,
    profile: null,
    status: 'new',
    reply: null,
    replied_at: null,
  };
  const s = readStored();
  writeStored({ ...s, local: [item, ...s.local] });
  return item;
}

export function updateFeedback(
  feedbackId: string,
  patch: { status?: FeedbackStatus; reply?: string | null },
): void {
  const s = readStored();
  const apply = (cur: Override): Override => ({
    status: patch.status ?? cur.status,
    reply: patch.reply !== undefined ? patch.reply : cur.reply,
    replied_at: patch.status === 'reflected' ? new Date().toISOString() : cur.replied_at,
  });

  const localIdx = s.local.findIndex((f) => f.feedback_id === feedbackId);
  if (localIdx >= 0) {
    const local = s.local.map((f) => (f.feedback_id === feedbackId ? { ...f, ...apply(f) } : f));
    writeStored({ ...s, local });
    return;
  }
  const cur = s.overrides[feedbackId] ?? { status: 'new', reply: null, replied_at: null };
  writeStored({ ...s, overrides: { ...s.overrides, [feedbackId]: apply(cur) } });
}

export function feedbackForProduct(list: Feedback[], productId: string): Feedback[] {
  return list.filter((f) => f.product_id === productId);
}

export function feedbackForBrand(list: Feedback[], brandName: string): Feedback[] {
  return list.filter((f) => f.brand_name === brandName);
}
