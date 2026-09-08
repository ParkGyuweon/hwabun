/**
 * 광고 표현 금지어 — 화장품법 제13조, 식약처 표시·광고 관리 지침(2025-08-14).
 * 출처: docs/dashboard/dashboard-redesign-spec.md §4-1 시스템 프롬프트의 [광고 표현 금지] 절.
 *
 * 사장님이 고객에게 보내는 답글은 광고물로 볼 수 있어서, 입력하는 동안 걸리는 표현을 바로 보여준다(F3).
 * 막지는 않는다 — 판단은 사장님 몫이고, 여기서는 "이 단어는 문제될 수 있다" 만 알린다.
 */

/** 쓰면 안 되는 표현. 질병 치료·의약품 오인 */
export const AD_FORBIDDEN: ReadonlyArray<{ term: string; why: string }> = [
  { term: '치료', why: '질병 치료 표현은 의약품 오인' },
  { term: '살균', why: '의약외품·의약품 효능' },
  { term: '소독', why: '의약외품·의약품 효능' },
  { term: '항염', why: '의약품 효능' },
  { term: '항균', why: '의약품 효능' },
  { term: '해독', why: '의약품 효능' },
  { term: '혈액순환', why: '신체 기능 개선 표현' },
  { term: '피부재생', why: '세포·조직 재생 표현' },
  { term: '피부 재생', why: '세포·조직 재생 표현' },
  { term: '세포 재생', why: '세포·조직 재생 표현' },
  { term: '세포재생', why: '세포·조직 재생 표현' },
  { term: '호르몬', why: '신체 기능 개선 표현' },
  { term: '홍조 개선', why: '질병 증상 개선' },
  { term: '홍반 개선', why: '질병 증상 개선' },
  { term: '홍조 제거', why: '질병 증상 개선' },
  { term: '홍반 제거', why: '질병 증상 개선' },
  { term: '뾰루지 개선', why: '질병 증상 개선' },
  { term: '상처 치료', why: '질병 치료 표현' },
  { term: '병원용', why: '의료기관 연관 오인' },
  { term: '피부과 전용', why: '의료기관 연관 오인' },
  { term: '엑소좀', why: '표시·광고 지침 금지 원료명' },
  { term: '마이크로니들', why: '의료기기 오인' },
  { term: '아토피', why: '질병명' },
  { term: '건선', why: '질병명' },
  { term: '소양증', why: '질병명' },
  { term: '여드름 치료', why: '질병 치료 표현' },
  { term: '기미 치료', why: '질병 치료 표현' },
  { term: '화상', why: '질병명' },
];

/** 실증자료가 있어야 쓸 수 있는 표현 */
export const AD_NEEDS_PROOF: ReadonlyArray<string> = [
  '여드름성 피부에 사용 적합',
  '다크서클 완화',
  '피부장벽 손상 개선',
  '피지분비 조절',
  '붓기 완화',
  '미세먼지 차단',
];

/** 기능성화장품 심사 제품에만 허용 */
export const AD_FUNCTIONAL_ONLY: ReadonlyArray<string> = ['미백', '주름 개선', '자외선 차단'];

export interface AdTermHit {
  term: string;
  level: 'forbidden' | 'proof' | 'functional';
  why: string;
}

const norm = (s: string) => s.replace(/\s+/g, '');

/** 본문에서 걸리는 표현. 공백을 지우고 비교해 "피부 재생"·"피부재생" 을 같이 잡는다 */
export function findAdTerms(text: string): AdTermHit[] {
  const t = norm(text);
  if (!t) return [];
  const hits: AdTermHit[] = [];
  for (const { term, why } of AD_FORBIDDEN) {
    if (t.includes(norm(term)) && !hits.some((h) => norm(h.term) === norm(term))) hits.push({ term, level: 'forbidden', why });
  }
  for (const term of AD_NEEDS_PROOF) {
    if (t.includes(norm(term))) hits.push({ term, level: 'proof', why: '실증자료 필요' });
  }
  for (const term of AD_FUNCTIONAL_ONLY) {
    if (t.includes(norm(term))) hits.push({ term, level: 'functional', why: '기능성화장품 심사 제품만' });
  }
  // "피부나이 n세 감소"
  if (/피부나이\d+세감소/.test(t)) hits.push({ term: '피부나이 n세 감소', level: 'forbidden', why: '수치 효능 단정' });
  return hits;
}
