/**
 * 알림이 새로 생겼다는 **같은 브라우저 안** 신호 (2026-10-01 유림님: 판매자가 반영을 누르자마자 쇼핑몰 종에 빨간 점이 떠야 한다).
 *
 * 알림 종은 정기 polling 을 하지 않는다 (백엔드 요청 2026-09-18). 그래서 대시보드와 쇼핑몰을 한 화면에 나란히 띄운 시연에서는
 * 쇼핑몰 탭이 "다시 보이게" 되는 순간이 없어 배지가 그대로였다. 알림을 만드는 쪽(판매자 응답 · 고객 의견)이 성공하면
 * 여기로 신호를 보내고, 같은 출처의 다른 탭·창에 떠 있는 종이 그 자리에서 안 읽은 수를 다시 받는다.
 *
 * 다른 기기·다른 브라우저에는 닿지 않는다 — 그쪽은 종의 5초 간격 확인(NotificationBell POLL_MS)이 받는다.
 * BroadcastChannel 이 없는 브라우저는 localStorage 의 storage 이벤트로 대신한다.
 */

const CHANNEL = 'hwabun.notifications.v1';
const STORAGE_KEY = 'hwabun.notifications.ping.v1';

let channel: BroadcastChannel | null = null;
function getChannel(): BroadcastChannel | null {
  if (channel) return channel;
  if (typeof BroadcastChannel === 'undefined') return null;
  try {
    channel = new BroadcastChannel(CHANNEL);
  } catch {
    channel = null;
  }
  return channel;
}

const local = new Set<() => void>();

/**
 * 알림을 만드는 요청이 성공한 뒤 부른다. BroadcastChannel 은 보내는 객체만 빼고 같은 탭의 다른 채널 객체에도 가므로
 * 이 탭의 종도 듣는다. storage 이벤트는 같은 탭에 오지 않아, 그 경우에만 이 탭 안에 직접 알린다.
 */
export function signalNotificationsChanged(): void {
  const ch = getChannel();
  if (ch) {
    ch.postMessage(Date.now());
    return;
  }
  try {
    window.localStorage.setItem(STORAGE_KEY, String(Date.now()));
  } catch {
    /* 저장이 막힌 환경 — 다른 탭은 탭 복귀 때 받는다 */
  }
  local.forEach((fn) => fn());
}

/** 신호를 듣는다. 해제 함수를 돌려준다 */
export function onNotificationsChanged(fn: () => void): () => void {
  // 보내는 채널 객체와 따로 연다 — 보낸 객체 자신에게는 메시지가 오지 않는다
  let rx: BroadcastChannel | null = null;
  if (typeof BroadcastChannel !== 'undefined') {
    try {
      rx = new BroadcastChannel(CHANNEL);
      rx.onmessage = () => fn();
    } catch {
      rx = null;
    }
  }
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) fn();
  };
  if (!rx) {
    local.add(fn);
    window.addEventListener('storage', onStorage);
  }
  return () => {
    if (rx) rx.close();
    else {
      local.delete(fn);
      window.removeEventListener('storage', onStorage);
    }
  };
}
