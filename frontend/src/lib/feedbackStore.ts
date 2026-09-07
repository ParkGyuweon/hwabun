/**
 * 피드백 저장소 — 쇼핑몰(index.html)과 대시보드(dashboard.html)가 같은 origin 이라
 * localStorage 로 건너간다. 대시보드에서 반영 처리하면 쇼핑몰 탭이 storage 이벤트로
 * 새로고침 없이 따라온다 (storefront.ts 와 같은 방식).
 *
 * 백엔드 Review·Feedback API 가 생기면 이 파일의 함수 본문만 fetch 로 바뀐다.
 */
import type { Feedback, FeedbackAspect, FeedbackStatus } from '../types/feedback';

export const FEEDBACK_KEY = 'hwabun.feedback.v1';

const listeners = new Set<() => void>();
let cache: Feedback[] | null = null;

function read(): Feedback[] {
  if (cache) return cache;
  try {
    const raw = window.localStorage.getItem(FEEDBACK_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    cache = Array.isArray(parsed) ? (parsed as Feedback[]) : [];
  } catch {
    cache = [];
  }
  return cache;
}

function write(list: Feedback[]): void {
  cache = list;
  try {
    window.localStorage.setItem(FEEDBACK_KEY, JSON.stringify(list));
  } catch {
    // 저장이 막힌 환경이면 메모리로만 산다
  }
  for (const l of listeners) l();
}

// 다른 탭(대시보드 ↔ 쇼핑몰)의 변경을 받는다
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key !== FEEDBACK_KEY) return;
    cache = null;
    for (const l of listeners) l();
  });
}

export function subscribeFeedback(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** `useSyncExternalStore` 스냅샷. 같은 내용이면 같은 배열 참조를 돌려준다 */
export function feedbackSnapshot(): Feedback[] {
  return read();
}

export function submitFeedback(input: {
  product_id: string;
  brand_name: string;
  persona_id: string | null;
  aspects: FeedbackAspect[];
  text: string;
}): Feedback {
  const item: Feedback = {
    feedback_id: `fb-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    product_id: input.product_id,
    brand_name: input.brand_name,
    persona_id: input.persona_id,
    aspects: input.aspects,
    text: input.text.trim(),
    purchased: false,
    created_at: new Date().toISOString(),
    status: 'new',
    reply: null,
    replied_at: null,
  };
  write([item, ...read()]);
  return item;
}

export function updateFeedback(
  feedbackId: string,
  patch: { status?: FeedbackStatus; reply?: string | null },
): void {
  write(
    read().map((f) =>
      f.feedback_id === feedbackId
        ? {
            ...f,
            ...(patch.status ? { status: patch.status } : {}),
            ...(patch.reply !== undefined ? { reply: patch.reply } : {}),
            ...(patch.status === 'reflected' ? { replied_at: new Date().toISOString() } : {}),
          }
        : f,
    ),
  );
}

export function feedbackForProduct(list: Feedback[], productId: string): Feedback[] {
  return list.filter((f) => f.product_id === productId);
}

export function feedbackForBrand(list: Feedback[], brandName: string): Feedback[] {
  return list.filter((f) => f.brand_name === brandName);
}
