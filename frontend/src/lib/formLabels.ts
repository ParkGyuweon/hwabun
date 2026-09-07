/**
 * 등록 폼 어휘와 한국어 라벨 — 단일 출처는 `contracts/product-form-labels-ko.json`.
 *
 * 화면은 `ko` 를 보여주고 저장·전송은 `value`(어휘집 원문)로 한다. 한 글자라도 바꾸면
 * 추천 벡터 매칭이 조용히 실패하므로 라벨 문자열을 코드에 두지 않는다.
 * (배너 쪽 `vocabLabels.ts` 와 같은 원칙. 두 파일은 185 에서 합친다.)
 */
import labels from '../../../contracts/product-form-labels-ko.json';

interface Entry {
  value: string;
  ko: string;
}
interface GroupMeta {
  group: 'concern' | 'clean' | 'texture';
  ko: string;
  hint: string;
}

const raw = labels as unknown as Record<string, unknown>;
const list = (key: string): Entry[] => (Array.isArray(raw[key]) ? (raw[key] as Entry[]) : []);

export const VOCAB_VERSION = String(raw.vocab_version ?? '');

/** highlights 30종 = concern 9 · clean 16 · texture 5. 성분은 태그로 받지 않는다 (계약 §3.1) */
export const HIGHLIGHT_GROUPS: ReadonlyArray<GroupMeta & { options: Entry[] }> = (
  Array.isArray(raw.highlights_groups) ? (raw.highlights_groups as GroupMeta[]) : []
).map((g) => ({ ...g, options: list(g.group) }));

export const HIGHLIGHT_VALUES: ReadonlySet<string> = new Set(
  HIGHLIGHT_GROUPS.flatMap((g) => g.options.map((o) => o.value)),
);
export const CONCERN_VALUES: ReadonlySet<string> = new Set(list('concern').map((o) => o.value));

export const SECONDARY_CATEGORIES: Entry[] = list('secondary_category');
export const TERTIARY_CATEGORIES: Entry[] = list('tertiary_category');

const ko = new Map<string, string>();
for (const key of ['concern', 'clean', 'texture', 'secondary_category', 'tertiary_category', 'ingredient']) {
  for (const e of list(key)) ko.set(e.value, e.ko);
}
export const labelKo = (value: string): string => ko.get(value) ?? value;
