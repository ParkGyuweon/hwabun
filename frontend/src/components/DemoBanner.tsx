import { useEffect } from 'react';
import '../styles/demo-banner.css';

/**
 * 발표용 상단 띠. 대시보드(사장님 화면)와 쇼핑몰(고객 화면)을 나란히 띄워 시연할 때
 * 멀리서도 어느 쪽인지 읽히게 화면 맨 위에 굵은 띠 하나를 두른다 (2026-09-22 유림님).
 *
 * **늘 켜져 있다** (2026-09-23 유림님). 전에는 `?demo=seller|shopper` 를 붙여야만 떴는데, 주소를 챙기지 않아도
 * 기존 대시보드·쇼핑몰 주소 그대로 띠가 보이게 바꿨다. 어느 띠인지는 붙인 쪽이 `role` 로 정한다.
 *
 * 쇼핑몰은 핑크, 대시보드는 연두. 끄는 스위치는 두지 않는다.
 *
 * 띠는 문서 흐름 안에 sticky 로 둔다. 화면의 다른 sticky 요소(대시보드 사이드바·쇼핑몰 헤더)는
 * demo-banner.css 가 `html[data-demo]` 아래에서 띠 높이만큼 내려 준다.
 */
export type DemoRole = 'seller' | 'shopper';

const TEXT: Record<DemoRole, { big: string; small: string }> = {
  seller: { big: '사장님 화면', small: 'HWABUN 브랜드 대시보드' },
  shopper: { big: '고객 화면', small: 'HWABUN 쇼핑몰' },
};

export default function DemoBanner({ role }: { role: DemoRole }) {
  useEffect(() => {
    document.documentElement.dataset.demo = role;
    return () => {
      delete document.documentElement.dataset.demo;
    };
  }, [role]);

  const t = TEXT[role];
  return (
    <div className={`demo-banner demo-banner--${role}`} role="note" aria-label={`${t.big} 시연`}>
      <span className="demo-banner__dot" aria-hidden="true" />
      <strong className="demo-banner__big">{t.big}</strong>
      <span className="demo-banner__small">{t.small}</span>
    </div>
  );
}
