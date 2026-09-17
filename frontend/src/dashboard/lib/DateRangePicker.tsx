import { useState } from 'react';
import { type DateRange, type PresetKey, MAX_PICKABLE_DATE, PRESET_LABEL, presetRange } from './dateRange';

const PRESET_KEYS: Exclude<PresetKey, 'custom'>[] = ['today', 'yesterday', 'last7', 'last30'];

/**
 * 기간 선택. 자주 쓰는 프리셋 네 개와, 특정 날짜를 직접 고르는 달력.
 *
 * 값이 어느 프리셋과도 안 맞으면(달력으로 고른 값) '직접 설정' 이 눌린 것으로 그린다 — 프리셋 버튼과
 * 달력이 서로 다른 상태를 들고 있지 않게, 진짜 값(`value`)에서 매번 되짚는다.
 */
export function DateRangePicker({ value, onChange }: { value: DateRange; onChange: (range: DateRange) => void }) {
  const [open, setOpen] = useState(false);

  const activePreset = PRESET_KEYS.find((k) => {
    const p = presetRange(k);
    return p.from === value.from && p.to === value.to;
  });

  return (
    <div className="daterange">
      <div className="daterange__presets" role="group" aria-label="조회 기간">
        {PRESET_KEYS.map((key) => (
          <button
            key={key}
            type="button"
            className={activePreset === key ? 'is-active' : ''}
            onClick={() => {
              onChange(presetRange(key));
              setOpen(false);
            }}
          >
            {PRESET_LABEL[key]}
          </button>
        ))}
        <button type="button" className={!activePreset ? 'is-active' : ''} onClick={() => setOpen((v) => !v)}>
          {!activePreset ? `${value.from} ~ ${value.to}` : PRESET_LABEL.custom}
        </button>
      </div>

      {open ? (
        <div className="daterange__calendar" role="group" aria-label="날짜 직접 설정">
          <label>
            시작일
            <input
              type="date"
              value={value.from}
              max={value.to}
              onChange={(event) => {
                const from = event.target.value;
                if (!from) return;
                onChange({ from, to: value.to < from ? from : value.to });
              }}
            />
          </label>
          <label>
            종료일
            <input
              type="date"
              value={value.to}
              min={value.from}
              max={MAX_PICKABLE_DATE}
              onChange={(event) => {
                const to = event.target.value;
                if (!to) return;
                onChange({ from: value.from > to ? to : value.from, to });
              }}
            />
          </label>
          <button type="button" className="daterange__done" onClick={() => setOpen(false)}>
            적용
          </button>
        </div>
      ) : null}
    </div>
  );
}
