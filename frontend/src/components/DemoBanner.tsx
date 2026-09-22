import { useEffect, useState } from 'react';
import '../styles/demo-banner.css';

/**
 * 발표용 상단 띠. 대시보드(사장님 화면)와 쇼핑몰(고객 화면)을 나란히 띄워 시연할 때
 * 멀리서도 어느 쪽인지 읽히게 화면 맨 위에 굵은 띠 하나를 두른다 (2026-09-22 유림님).
 *
 * 켜는 법: 주소 뒤에 `?demo=seller`(대시보드) 또는 `?demo=shopper`(쇼핑몰). 끄는 법: `?demo=off`.
 * 쇼핑몰은 상품을 누를 때 주소를 바꿔 쓰므로 한 번 켠 값은 sessionStorage 에 기억해 탭을 닫을 때까지 유지한다.
 * 평소 화면에는 아무 흔적도 없다 — 값이 없으면 아무것도 그리지 않는다.
 *
 * 띠는 문서 흐름 안에 sticky 로 둔다. 화면의 다른 sticky 요소(대시보드 사이드바·쇼핑몰 헤더)는
 * demo-banner.css 가 `html[data-demo]` 아래에서 띠 높이만큼 내려 준다.
 */
type DemoRole = 'seller' | 'shopper';

const KEY = 'hwabun.demo-banner';

const TEXT: Record<DemoRole, { big: string; small: string }> = {
  seller: { big: '사장님 화면', small: 'HWABUN 브랜드 대시보드' },
  shopper: { big: '고객 화면', small: 'HWABUN 쇼핑몰' },
};

function readRole(): DemoRole | null {
  const q = new URLSearchParams(window.location.search).get('demo');
  if (q === 'seller' || q === 'shopper') {
    try {
      window.sessionStorage.setItem(KEY, q);
    } catch {
      /* 저장 못 해도 이번 화면에는 띄운다 */
    }
    return q;
  }
  if (q === 'off') {
    try {
      window.sessionStorage.removeItem(KEY);
    } catch {
      /* 무시 */
    }
    return null;
  }
  try {
    const saved = window.sessionStorage.getItem(KEY);
    return saved === 'seller' || saved === 'shopper' ? saved : null;
  } catch {
    return null;
  }
}

/** 마지막 조작 뒤 이만큼 지나면 다시 조용해진다 */
const ACTIVE_MS = 1200;

export default function DemoBanner() {
  const [role] = useState<DemoRole | null>(() => readRole());
  /**
   * 이 화면을 지금 만지고 있나. 누르기·끌기·스크롤·타자 같은 조작이 있으면 잠깐 켜진다.
   * 두 화면을 나란히 띄운 발표에서 "지금 어느 쪽을 조작 중인지" 가 띠의 흰 빛 움직임으로 보이게 (2026-09-22 유림님).
   */
  const [active, setActive] = useState(false);

  useEffect(() => {
    if (!role) return;
    document.documentElement.dataset.demo = role;
    return () => {
      delete document.documentElement.dataset.demo;
    };
  }, [role]);

  useEffect(() => {
    if (!role) return;
    let timer: number | undefined;
    const poke = () => {
      setActive(true);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setActive(false), ACTIVE_MS);
    };
    // passive 로 붙여 스크롤·터치 성능에 영향이 없게. capture 로 붙여 어느 요소가 막아도 받는다
    const opts: AddEventListenerOptions = { passive: true, capture: true };
    const events = ['pointerdown', 'pointermove', 'wheel', 'keydown', 'touchstart', 'scroll'] as const;
    for (const e of events) window.addEventListener(e, poke, opts);
    return () => {
      window.clearTimeout(timer);
      for (const e of events) window.removeEventListener(e, poke, opts);
    };
  }, [role]);

  if (!role) return null;
  const t = TEXT[role];
  return (
    <div className={`demo-banner demo-banner--${role}${active ? ' is-active' : ''}`} role="note" aria-label={`${t.big} 시연`}>
      <span className="demo-banner__dot" aria-hidden="true" />
      <strong className="demo-banner__big">{t.big}</strong>
      <span className="demo-banner__small">{t.small}</span>
    </div>
  );
}
