/**
 * 상품 문구 광고 금지 표현 — 판매자 상품 등록 화면에서 입력하는 동안 걸리는 낱말을 알려 준다.
 *
 * 목록은 `contracts/cosmetic-claim-banned-terms.json` 하나다(화장품법 제13조 · 식약처 표시·광고 지침).
 * AI 문장 필터(batch/serving/prescription.py)와 상품 문구 검사(contracts/tests/test_product_copy_claims.py)가
 * 같은 파일을 본다. 상품 문구에는 `product_copy` 절의 규칙(대시보드 전용 그룹 제외 · 뿌리 낱말 추가 ·
 * 오탐 허용 · 바꿀 말)을 쓴다. 정규화도 같다: NFC 후 글자·숫자만 남기고 부분 일치.
 *
 * 막지는 않는다. 등록은 그대로 되고, 칸 밑에 "이렇게 바꿔 주세요" 만 보여 준다.
 */
import terms from '../../../contracts/cosmetic-claim-banned-terms.json';

const norm = (s: string) => s.normalize('NFC').replace(/[^\p{L}\p{N}]/gu, '');

const pc = terms.product_copy;
const skip = new Set<string>(pc.skip_groups);
const exempt = new Set<string>(pc.exempt_terms);
const BANNED: string[] = [
  ...new Set([
    ...Object.entries(terms.banned)
      .filter(([group]) => !skip.has(group))
      .flatMap(([, ws]) => ws)
      .filter((w) => !exempt.has(w)),
    ...pc.extra_banned,
  ]),
];
const ALLOW: string[] = [...terms.allow.terms, ...pc.allow];
const HINTS: Record<string, string> = pc.hints;

export interface ClaimHit {
  term: string;
  /** 대신 쓸 말. 없으면 null */
  hint: string | null;
}

function hintFor(term: string): string | null {
  if (HINTS[term]) return HINTS[term];
  // "상처 치료" 처럼 힌트가 없으면 안에 든 뿌리 낱말(치료)의 힌트를 쓴다. 긴 것부터
  const root = Object.keys(HINTS)
    .filter((k) => norm(term).includes(norm(k)))
    .sort((a, b) => norm(b).length - norm(a).length)[0];
  return root ? HINTS[root] : null;
}

/** 문장에서 걸리는 금지 표현. "피부 재생" 이 걸리면 그 안의 "재생" 은 따로 알리지 않는다 */
export function findClaimTerms(text: string): ClaimHit[] {
  let raw = text ?? '';
  for (const a of ALLOW) raw = raw.split(a).join(' ');
  const t = norm(raw);
  if (!t) return [];
  const found = BANNED.filter((w) => norm(w) && t.includes(norm(w)));
  const kept = found.filter((w) => !found.some((o) => o !== w && norm(o).length > norm(w).length && norm(o).includes(norm(w))));
  const seen = new Set<string>();
  // "피부재생"·"피부 재생" 처럼 띄어쓰기만 다른 꼴은 하나로. 사장님이 실제로 쓴 꼴을 남긴다
  return [...kept.filter((w) => raw.includes(w)), ...kept.filter((w) => !raw.includes(w))]
    .filter((w) => (seen.has(norm(w)) ? false : (seen.add(norm(w)), true)))
    .map((term) => ({ term, hint: hintFor(term) }));
}

/** 받침이 있으면 '은', 없으면 '는' ("‘최상’은", "‘치료’는") */
function topic(word: string): string {
  const code = word.charCodeAt(word.length - 1) - 0xac00;
  return code >= 0 && code < 11172 && code % 28 !== 0 ? '은' : '는';
}

/** 사장님께 보여 줄 한 줄 */
export function claimMessage(hit: ClaimHit): string {
  const head = `‘${hit.term}’${topic(hit.term)} 화장품 광고에 쓸 수 없는 표현이에요.`;
  return hit.hint ? `${head} ‘${hit.hint}’처럼 바꿔 주세요.` : `${head} 다른 말로 바꿔 주세요.`;
}
