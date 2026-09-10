/**
 * 고객 피드백 — 참여 루프 ①(남김) → ②(사장이 분류별로 본다) → ③(고친다) → ④(반영됐다고 돌려준다).
 *
 * 계약: `contracts/feedback-classification.md` + `contracts/feedback-category-vocab.json` (Jira 200).
 * 리뷰가 아니다. 사장님에게 보내는 **개선 요청**이라 별점·극성이 없고 전부 "고쳐 달라"로 본다.
 *
 * 분류는 소비자가 고르지 않는다. 텍스트를 분류기(Jira 201)가 어휘 목록에서 **딱 하나**
 * (축 1 + 카테고리 1) 고른다. FE 가 임시로 두었던 8종 다중 선택은 이 계약으로 갈아탔다.
 * 서버가 생기면 백엔드 Feedback API(Jira 146)로 옮긴다. 그때까지 localStorage.
 * 로그에는 원문을 싣지 않는다 (behavior-log-design "일부러 안 남기는 것").
 */
import vocab from '../../../contracts/feedback-category-vocab.json';
import type { SkinType } from './product';

interface VocabCategory {
  id: string;
  label: string;
  desc: string;
}
interface VocabAxis {
  id: string;
  label: string;
  desc: string;
  categories: VocabCategory[];
}
interface Vocab {
  schema_version: string;
  axes: VocabAxis[];
  other: VocabCategory;
}

const v = vocab as unknown as Vocab;

export const FEEDBACK_VOCAB_VERSION = v.schema_version;

/** 축 5개 + 기타. 화면 탭 순서 = 어휘 파일 순서 */
export const FEEDBACK_AXES: ReadonlyArray<VocabAxis> = [
  ...v.axes,
  { id: v.other.id, label: v.other.label, desc: v.other.desc, categories: [v.other] },
];

const axisById = new Map(FEEDBACK_AXES.map((a) => [a.id, a]));
const categoryById = new Map(FEEDBACK_AXES.flatMap((a) => a.categories.map((c) => [c.id, { ...c, axis_id: a.id }])));

export const axisLabel = (id: string): string => axisById.get(id)?.label ?? id;
export const categoryLabel = (id: string): string => categoryById.get(id)?.label ?? id;
export const categoryDesc = (id: string): string => categoryById.get(id)?.desc ?? '';

export type FeedbackStatus = 'new' | 'read' | 'reflected';

/** 계약 0.2.0 §4 `labels[]` 원소. 전부 입력 축 안의 카테고리 */
export interface FeedbackLabel {
  axis_id: string;
  axis: string;
  category_id: string;
  category: string;
}

/**
 * 계약 §3 입력 + §4 출력 + FE 전용 필드.
 *
 * 분류 필드는 분류기가 돌기 전엔 `null` 이다. 서버가 없는 지금은 쇼핑몰에서 새로 쓴 글이
 * 그 상태로 남고, 시드 30건은 분류기 결과를 그대로 싣는다.
 */
export interface Feedback {
  // ---- 계약 §3 입력 (FE → 분류기)
  feedback_id: string;
  /** 작성자. 프로필 조인 키. 비로그인은 null (계약은 필수지만 이 사이트엔 로그인이 없다) */
  user_id: string | null;
  product_id: string;
  body: string;
  created_at: string;

  // ---- 계약 0.2.0 §3 입력: 축은 고객이 토글로 고른다
  axis_id: string | null;
  axis: string | null;

  // ---- 계약 0.2.0 §4 출력 (분류기 → 저장 → 대시보드). 분류 전 labels = []
  /** 문장에 실제로 적힌 불만만, 전부 입력 축 안. **집계 단위는 언급 수** — 한 건이 두 칸에 뜰 수 있다 */
  labels: FeedbackLabel[];
  /** labels[0]. 대표 표시·정렬용 */
  primary: FeedbackLabel | null;
  /** 다른 축 얘기로 보일 때 축 id. 참고용·보장 없음. 화면은 무시한다 (계약 §4) */
  off_axis_hint: string | null;
  /** = primary. 0.1.0 소비자 호환용. 새 코드는 labels 를 읽는다 */
  category_id: string | null;
  category: string | null;
  classifier: string | null;
  vocab_version: string | null;
  classified_at: string | null;
  /** 본문에서 걸린 금지어 (Jira 202). 없으면 [] */
  banned_terms: string[];
  /** true 면 대시보드가 본문을 접어 두고 눌러야 보여준다. 집계에는 그대로 포함 */
  hidden_by_default: boolean;

  // ---- FE 전용
  /** 대시보드 브랜드 스코프 필터. 서버가 생기면 product_id → brand 조인으로 대체 */
  brand_name: string;
  /** 비익명 계약 — 사장님 화면에 작성자 피부를 보여도 된다. 지금은 시드에만 있고 나중엔 user_id 조인 */
  profile: { skin_type: SkinType | string; skin_tone: string } | null;
  status: FeedbackStatus;
  /** 사장님이 반영하며 남긴 한 줄. 소비자에게 그대로 보인다 (루프 ④) */
  reply: string | null;
  replied_at: string | null;
  /** 백엔드(GET /api/seller/feedback)에서 온 행. 없으면 로컬 저장 */
  source?: 'backend';
}

/** 고객이 고를 수 있는 축 5개. `other` 는 0.2.0 부터 축이 아니라 "그 축 얘기지만 목록에 없는 불만" 카테고리라 토글에 없다 */
export const FEEDBACK_INPUT_AXES: ReadonlyArray<VocabAxis> = v.axes;

/** 분류기가 아직 안 돈 행. 0.2.0 부터 축은 고객이 고르므로 라벨이 비었는지로 본다 */
export const isUnclassified = (f: Feedback): boolean => labelsOf(f).length === 0;

/** 라벨 목록. 0.1.0 형태(단일 category_id)로 저장된 옛 행도 한 개짜리 목록으로 읽는다 */
export function labelsOf(f: Feedback): FeedbackLabel[] {
  if (f.labels && f.labels.length > 0) return f.labels;
  if (f.category_id && f.axis_id) {
    return [{ axis_id: f.axis_id, axis: f.axis ?? axisLabel(f.axis_id), category_id: f.category_id, category: f.category ?? categoryLabel(f.category_id) }];
  }
  return [];
}
