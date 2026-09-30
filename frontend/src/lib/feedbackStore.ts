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
const SEED_IDS = new Set(SEED.map((r) => r.feedback_id));
const EMPTY: Stored = { overrides: {}, local: [] };

/** 번들 샘플 파일에서 온 행인가. 대시보드가 "실측/시드" 배지를 가르는 기준 */
export const isSeedFeedback = (f: Pick<Feedback, 'feedback_id'>): boolean => SEED_IDS.has(f.feedback_id);

/**
 * 목록의 출처 배지. 백엔드에서 받았거나 이 사이트에서 쓴 글이 한 건이라도 있으면 `real`,
 * 전부 번들 샘플이면 `seed`. 샘플 30건을 "실측" 이라 부르면 사장님이 진짜 고객 글로 읽는다
 */
export const feedbackSource = (list: Pick<Feedback, 'feedback_id'>[]): 'real' | 'seed' =>
  list.some((f) => !isSeedFeedback(f)) ? 'real' : 'seed';

/**
 * 진짜 의견이 한 건이라도 있으면 번들 샘플은 뺀다. 샘플만 있으면 그대로 두고, 화면이 한 건마다 "예시" 를 붙인다.
 * 지금 스냅샷은 샘플을 섞지 않지만(아래 feedbackSnapshot), 예전 저장본·서버 응답에 샘플 id 가 섞여 와도
 * 진짜 의견과 한데 세지 않도록 두 화면(고객의 말·요약)이 이 함수를 거친다 (2026-09-29).
 */
export function dropSamplesIfReal<T extends Pick<Feedback, 'feedback_id'>>(list: T[]): T[] {
  return list.some((f) => !isSeedFeedback(f)) ? list.filter((f) => !isSeedFeedback(f)) : list;
}

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
  /*
   * 번들 샘플 30건을 더 이상 섞지 않는다 (2026-09-17).
   * 배지에 '시드' 라고 적어 두긴 했지만, 화면에는 고객이 쓴 것처럼 생긴 문장이 30개 떠 있었고 사장님은
   * 그것을 자기 고객의 말로 읽는다. 없으면 없다고 적는다.
   *
   * `SEED`·`isSeedFeedback` 은 남긴다 — 예전에 저장된 override 가 시드 id 를 가리킬 수 있어서, 그 판정이
   * 사라지면 지운 글이 되살아난 것처럼 보인다.
   */
  void fresh;
  snapshot = [...s.local].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
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
