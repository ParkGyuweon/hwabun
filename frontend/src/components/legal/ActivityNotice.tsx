import { useState } from 'react';
import type { MouseEvent } from 'react';

/** 판을 올리면(방침 내용이 크게 바뀌면) 다시 보여 준다 */
const DISMISS_KEY = 'bloom.activity-notice.v1';

function wasDismissed(): boolean {
  try {
    return window.localStorage.getItem(DISMISS_KEY) === '1';
  } catch {
    return false;
  }
}

function rememberDismissed(): void {
  try {
    window.localStorage.setItem(DISMISS_KEY, '1');
  } catch {
    // 저장이 막힌 브라우저(사생활 보호 모드 등)면 이번 화면에서만 닫힌다
  }
}

/**
 * 첫 방문 안내. 둘러본 기록을 모은다는 사실을 알린다.
 *
 * **알리기만 한다.** 확인을 누르든 말든 기록은 계속 모은다 (결정 A3). 그래서 "동의" 가 아니라 "확인" 이다.
 * 왼쪽 아래에 둔다 — 오른쪽 아래는 다른 떠 있는 창 자리다.
 */
export default function ActivityNotice({ onOpenPrivacy }: { onOpenPrivacy: () => void }) {
  const [open, setOpen] = useState(() => !wasDismissed());
  if (!open) return null;

  const openPrivacy = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    onOpenPrivacy();
  };

  return (
    <div className="activity-notice" role="status" aria-live="polite">
      <p className="activity-notice__text">
        더 나은 추천을 위해 둘러보신 기록을 모아요. 자세한 내용은{' '}
        <a href="?privacy=1" onClick={openPrivacy}>
          개인정보처리방침
        </a>
        에서 볼 수 있어요.
      </p>
      <button
        type="button"
        className="activity-notice__ok"
        onClick={() => {
          rememberDismissed();
          setOpen(false);
        }}
      >
        확인
      </button>
    </div>
  );
}
