import { useSyncExternalStore } from 'react';
import { feedbackSnapshot, subscribeFeedback } from '../lib/feedbackStore';
import type { Feedback } from '../types/feedback';

/** 피드백 전체. 다른 탭에서 바뀌어도 따라온다 */
export function useFeedback(): Feedback[] {
  return useSyncExternalStore(subscribeFeedback, feedbackSnapshot, feedbackSnapshot);
}
