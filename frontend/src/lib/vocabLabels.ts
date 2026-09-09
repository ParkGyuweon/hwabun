/**
 * 어휘 값 → 한국어 라벨. 단일 출처는 `contracts/product-form-labels-ko.json` 이다.
 *
 * 화면은 `ko` 를 보여주고 서버·로그로는 `value`(어휘집 원문)를 보낸다. 라벨 문자열을
 * 코드에 적어 두면 어휘집이 바뀔 때 조용히 갈라지므로, 여기 말고는 라벨을 두지 않는다.
 * 매칭이 안 되면 원문을 그대로 돌려준다 — 화면에 영문이 보이는 편이 빈칸보다 낫고,
 * 그게 어휘가 어긋났다는 신호다.
 */
import labels from '../../../contracts/product-form-labels-ko.json';
import type { BannerType } from '../types/log';

interface LabelEntry {
  value: string;
  ko: string;
  field?: string;
}

const raw = labels as unknown as Record<string, unknown>;

function table(key: string): Map<string, string> {
  const list = raw[key];
  const map = new Map<string, string>();
  if (Array.isArray(list)) {
    for (const item of list as LabelEntry[]) map.set(item.value, item.ko);
  }
  return map;
}

const TABLES = {
  concern: table('concern'),
  ingredient: table('ingredient'),
  clean: table('clean'),
  price_bin: table('price_bin'),
  secondary_category: table('secondary_category'),
  tertiary_category: table('tertiary_category'),
  segment: table('segment'),
};

export const VOCAB_LABEL_VERSION = String(raw.vocab_version ?? '');

/** 배너 축 값의 라벨. `category` 는 secondary 를 먼저 보고 tertiary 를 본다 */
export function bannerValueLabel(type: BannerType, value: string | null): string {
  if (value === null) return '';
  switch (type) {
    case 'concern':
      return TABLES.concern.get(value) ?? value;
    case 'ingredient':
      return TABLES.ingredient.get(value) ?? value;
    case 'clean':
      return TABLES.clean.get(value) ?? value;
    case 'price_bin':
      return TABLES.price_bin.get(value) ?? value;
    case 'category':
      return TABLES.secondary_category.get(value) ?? TABLES.tertiary_category.get(value) ?? value;
    case 'segment':
      return TABLES.segment.get(value) ?? value;
    case 'new_brand':
      return '';
    default:
      return value;
  }
}

export const concernLabel = (value: string): string => TABLES.concern.get(value) ?? value;
export const segmentLabel = (value: string): string => TABLES.segment.get(value) ?? value;
export const categoryLabel = (value: string): string =>
  TABLES.secondary_category.get(value) ?? TABLES.tertiary_category.get(value) ?? value;

/** 어휘집에 있는 clean 태그만 골라낸다 (highlights 에는 수상·커뮤니티 배지도 섞여 있다) */
export const CLEAN_VALUES: ReadonlySet<string> = new Set(TABLES.clean.keys());
