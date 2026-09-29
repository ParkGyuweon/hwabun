/**
 * 여러 칸 중 "가장 많이 담는 칸" 을 고를 때 우연을 덜 타게 하는 도구.
 *
 * 칸이 스무 개면 방문이 적은 칸 하나는 운으로 비율이 튄다. 원래 비율 대신
 * **윌슨 95% 하한**(이 칸의 진짜 비율이 적어도 이만큼은 된다고 말할 수 있는 값)으로
 * 줄 세우면, 방문이 적은 칸은 하한이 낮아져 저절로 뒤로 밀린다. 화면에는 여전히
 * 원래 비율을 적는다 · 고르는 기준만 바꾼다.
 */

const Z = 1.96;

/** 윌슨 95% 하한. rate 는 0~1, n 은 표본 수. n 이 0 이면 0 */
export function wilsonLower(rate: number, n: number): number {
  if (n <= 0) return 0;
  const p = Math.min(1, Math.max(0, rate));
  const z2 = Z * Z;
  const centre = p + z2 / (2 * n);
  const margin = Z * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n));
  return Math.max(0, (centre - margin) / (1 + z2 / n));
}

/** 하한이 가장 큰 항목. 비어 있으면 null */
export function pickByLowerBound<T>(items: readonly T[], rate: (t: T) => number, n: (t: T) => number): T | null {
  let best: T | null = null;
  let bestLb = -1;
  for (const it of items) {
    const lb = wilsonLower(rate(it), n(it));
    if (lb > bestLb) {
      best = it;
      bestLb = lb;
    }
  }
  return best;
}

/**
 * 하한이 원래 비율보다 3분의 1 넘게 낮으면 "표본이 적어 참고만" 으로 적는다.
 * 예: 담기 10% 인 칸은 방문 50건이면 하한 약 4% (표시), 500건이면 약 8% (표시 안 함).
 */
export function isThinEstimate(rate: number, n: number): boolean {
  if (rate <= 0) return false;
  return rate - wilsonLower(rate, n) > rate / 3;
}
