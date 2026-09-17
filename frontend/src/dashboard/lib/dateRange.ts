/**
 * 주문 화면의 조회 기간. KST 날짜 문자열(`YYYY-MM-DD`) 쌍이다.
 *
 * 행동 마트가 쓰는 `days`(7·14·30) 와 다르다. 주문은 쇼핑몰 원장을 직접 읽어서 임의의 시작·끝 날짜를
 * 그대로 받을 수 있고, 사장님이 "지난달 이맘때" 처럼 구체적인 기간을 물어보는 자리라 프리셋 몇 개로는
 * 부족하다. 그래서 여기는 달력으로 직접 고르는 길을 같이 둔다.
 */

/** KST 자정 기준 오늘. `Date` 의 로컬 타임존이 무엇이든 KST 날짜로 고정한다 */
function todayKst(): Date {
  const kstNow = new Date(Date.now() + 9 * 60 * 60 * 1000);
  return new Date(Date.UTC(kstNow.getUTCFullYear(), kstNow.getUTCMonth(), kstNow.getUTCDate()));
}

const iso = (d: Date): string => d.toISOString().slice(0, 10);

function addDays(d: Date, n: number): Date {
  const out = new Date(d);
  out.setUTCDate(out.getUTCDate() + n);
  return out;
}

export type DateRange = { from: string; to: string };

export type PresetKey = 'today' | 'yesterday' | 'last7' | 'last30' | 'custom';

export const PRESET_LABEL: Record<PresetKey, string> = {
  today: '오늘',
  yesterday: '어제',
  last7: '최근 7일',
  last30: '최근 30일',
  custom: '직접 설정',
};

/** 프리셋 하나를 실제 날짜 범위로. `custom` 은 여기서 만들지 않는다 — 달력에서 고른 값을 그대로 쓴다 */
export function presetRange(key: Exclude<PresetKey, 'custom'>): DateRange {
  const today = todayKst();
  switch (key) {
    case 'today':
      return { from: iso(today), to: iso(today) };
    case 'yesterday': {
      const y = addDays(today, -1);
      return { from: iso(y), to: iso(y) };
    }
    case 'last7':
      return { from: iso(addDays(today, -6)), to: iso(today) };
    case 'last30':
      return { from: iso(addDays(today, -29)), to: iso(today) };
  }
}

/** 오늘 이후 날짜는 고를 수 없다. `<input type="date">` 의 `max` 에 쓴다 */
export const MAX_PICKABLE_DATE = iso(todayKst());
