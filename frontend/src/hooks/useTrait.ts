import { useSyncExternalStore } from 'react';
import { subscribeTrait, traitDecisionSnapshot } from '../lib/trait';
import type { TraitDecision } from '../lib/trait';

/**
 * 세션 성향 결정. 이벤트가 쌓일 때마다 다시 계산된다.
 *
 * 배너 화면이 이 값의 `axes` 를 추천 API 에 실어 보내고, `trait_source` 와
 * `snapshot` 을 `banner_impression` / `banner_click` property 에 남긴다.
 * 감쇠는 시간 함수라 렌더 사이에 조금씩 달라지지만, 배너는 이벤트가 올 때만
 * 다시 그리면 충분하다.
 */
export function useTrait(): TraitDecision {
  return useSyncExternalStore(subscribeTrait, traitDecisionSnapshot, traitDecisionSnapshot);
}
