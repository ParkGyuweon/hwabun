import { useRef } from 'react';
import type { MouseEvent } from 'react';

/**
 * 모달 배경을 **눌렀다 뗀** 경우에만 닫는 핸들러.
 *
 * `onClick={onClose}` 만 두면 폼 안에서 글자를 드래그하다 마우스를 배경 위에서 놓을 때도 닫힌다 —
 * 브라우저의 `click` 은 mousedown 과 mouseup 이 다른 요소여도 두 요소의 공통 조상(여기서는 배경)에서
 * 발생하기 때문이다. 이메일을 긁어 복사하려다 로그인 창이 사라지는 일이 그것이다 (2026-09-17 보고).
 *
 * 그래서 mousedown 이 배경 자체에서 시작했는지 기억해 두고, click 도 배경 자체에서 끝났을 때만 닫는다.
 * 카드 안쪽에서 시작한 어떤 동작도 창을 닫지 못한다.
 */
export function useBackdropClose(onClose: () => void) {
  const armed = useRef(false);

  return {
    onMouseDown: (event: MouseEvent<HTMLElement>) => {
      armed.current = event.target === event.currentTarget;
    },
    onClick: (event: MouseEvent<HTMLElement>) => {
      const onBackdrop = event.target === event.currentTarget;
      const shouldClose = armed.current && onBackdrop;
      armed.current = false;
      if (shouldClose) onClose();
    },
  };
}
