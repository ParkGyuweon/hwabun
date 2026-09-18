/**
 * AI 가 정리한 고객 목소리 — 판매자 대시보드가 읽는 모양.
 *
 * 계약: contracts/feedback-insight-spec.md (초안 0.1, 2026-09-18).
 * 흐름: 프론트 → 백엔드 DB(feedback·review 원문) → 추천 서비스(LLM 취합) → 백엔드 저장 → 이 화면.
 * 갱신은 매일 06:00 한 번 + 사장님이 "즉시 반영" 을 누른 때. 프론트는 만들지 않고 읽기만 한다.
 *
 * 필드는 전부 서버가 준 그대로 싣는다. 값이 비면 화면이 "없음" 을 적는다 — 프론트가 채워 넣지 않는다.
 */

export type InsightSource = 'scheduled' | 'manual';

/** 근거 한 줄. 원문 id 로 아래 목록의 글과 이어진다 */
export interface InsightEvidence {
  type: 'feedback' | 'review';
  id: string;
  /** 원문에서 잘라 온 한 문장. 서버가 고른다 */
  quote: string;
  productId?: string | null;
}

export interface InsightSummary {
  /** 가장 많이 나온 불만. 많은 순, 최대 3 */
  topComplaints: Array<{ text: string; count: number; axisId?: string | null }>;
  /** 사지 않은 사람이 남긴 이유. 비구매자 피드백에서만 뽑는다 */
  preBuyDropReasons: Array<{ text: string; count: number }>;
  /** 가격을 언급한 글의 비율 (0~1). 글이 없으면 null */
  priceMentionRate: number | null;
  /** 지금 할 일. 짧은 명령문, 최대 3 */
  actions: string[];
}

export interface SellerInsight {
  brandId: string;
  /** 상품 하나로 좁힌 요약이면 그 id, 브랜드 전체면 null */
  productId: string | null;
  generatedAt: string;
  source: InsightSource;
  /** 요약에 들어간 글 수 */
  inputCount: { feedback: number; review: number };
  /** generatedAt 이후 새로 쌓인 글 수. 버튼을 누를 이유가 된다 */
  newSince: number;
  summary: InsightSummary;
  evidence: InsightEvidence[];
  model?: string | null;
}

/** 즉시 반영 요청의 결과 */
export type RefreshResult =
  | { kind: 'done'; insight: SellerInsight }
  | { kind: 'accepted'; jobId: string }
  /** 서버가 거부. 연타·새 글 없음. `retryAfterSec` 이 있으면 그만큼 버튼을 잠근다 */
  | { kind: 'rejected'; reason: string; retryAfterSec: number | null }
  | { kind: 'unavailable' };

export type RefreshJobState = 'running' | 'done' | 'failed';
