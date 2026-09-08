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

  // ---- 계약 §4 출력 (분류기 → 저장 → 대시보드). 분류 전 null
  axis_id: string | null;
  axis: string | null;
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
}

/** 분류기가 아직 안 돈 행. 화면에서 "분류 대기"로 묶는다 */
export const isUnclassified = (f: Feedback): boolean => f.axis_id === null;
