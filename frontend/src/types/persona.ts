import type { SkinType } from './product';

/**
 * 가상 페르소나. 이 사이트에는 로그인이 없고 이것이 로그인에 해당한다.
 *
 * 데이터 파트가 만든 표(`simulator/personas/data/personas_100_agent.json`)를 그대로
 * 쓴다. 여기서 고른 `persona_id` 가 모든 로그에 실리므로 **ID 체계가 그쪽과
 * 같아야** 조인이 된다.
 *
 * `PA` 접두사는 인터랙티브 전용 대역이라는 뜻이다. 합성 로그가 만들어지지 않아서
 * 사람이 누른 행동이 묻히지 않는다. `PC` 대역은 1인당 590건이 이미 쌓여 있어
 * 화면에 올리면 안 된다.
 *
 * 속성은 로그에 싣지 않는다. 백엔드가 `persona_id` 로 조인해서 쓴다.
 * 이벤트마다 속성을 실으면 페르소나 정의가 바뀔 때 과거 로그가 거짓말을 한다.
 */
export interface PersonaProfile {
  persona_id: string;
  skin_type: SkinType;
  skin_tone: string;
  eye_color: string;
  hair_color: string;
  /** 이 사람이 원본에서 남긴 리뷰 수 (3~19건) */
  n_reviews: number;
}
