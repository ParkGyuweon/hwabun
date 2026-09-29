/**
 * 개요 "지금 손봐야 할 것 한 줄" — 후보를 모아 점수로 하나만 고른다 (명세 O1).
 *
 * 점수 = |편차| × ln(표본). 편차는 기준(평균·기준선·코호트)에서 얼마나 떨어졌나를
 * 지표마다 0~1 로 정규화한 값이다. 표본이 작으면 편차가 커도 뒤로 간다.
 * 규칙 (ai-insight-rules §4-3):
 *   - n < 200 은 후보에서 뺀다
 *   - 결론에는 뷰티 명사(성분·피부타입·고민·콘텐츠)가 있어야 한다. 퍼널처럼 명사가 없는
 *     후보는 뷰티 후보가 하나도 없을 때만 올라온다
 *   - 인과를 단정하지 않는다. "~일 가능성"
 *   - 막힌 기록는 상품 선호로 읽지 않는다 (여기 후보에 넣지 않는다. 막히는 곳 화면 몫)
 *
 * 입력은 행동 지표 묶음(BehaviorMetrics)이다. 모의든 마트든 같은 모양이라 규칙은 하나다.
 */
import { labelKo } from '../../lib/formLabels';
import type { DataOrigin } from '../components';
import type { BehaviorMetrics, FunnelStep } from './behavior';
import { SKIN_TYPE_KO, fmt } from './metrics';
import { josa } from '../../lib/format';

export interface Insight {
  id: string;
  /**
   * 이 결론의 **근거가 어디서 왔나** (`components.tsx` DataOrigin 과 같은 축).
   *   mine    내 브랜드 상품의 행동·리뷰·피드백만으로 낸 것 (경계 문서 A층) → 연두
   *   shared  플랫폼 전체(다른 브랜드 포함)를 종합해 낸 것 (B·C층) → 핑크
   * "고객이 찾는 성분" 은 내 고객이 아니라 플랫폼 전체 고객의 관심이다. 같은 색으로 놓으면 내 가게 이야기로 읽힌다.
   */
  origin: DataOrigin;
  /** 어느 화면으로 가면 근거가 있나 */
  screen: 'content' | 'segments' | 'ingredients' | 'products' | 'behavior';
  headline: string;
  reasons: string[];
  action: string;
  /** 권고가 어느 단위인가 */
  unit: '상세페이지' | '고객·문구' | '제품·처방' | '포장' | '가격';
  n: number;
  confidence: '높음' | '보통' | '낮음';
  score: number;
  beautyNoun: boolean;
}

const TONE_KO: Record<string, string> = { fair: '가장 밝은 톤', light: '밝은 톤', medium: '중간 톤', tan: '어두운 톤', deep: '가장 어두운 톤' };

function conf(n: number, signals: number): Insight['confidence'] {
  if (n >= 1000 && signals >= 2) return '높음';
  if (n >= 200) return '보통';
  return '낮음';
}

export interface Verdict {
  headline: string;
  reason: string;
  action: string;
  sampleSize: number;
}

/**
 * 가장 크게 새는 구간을 찾아 한 문장으로 만든다.
 *
 * 경영진은 5초 안에 핵심을 파악해야 하고, 브랜드가 분석 도구에 갖는 최대 불만이
 * "수집은 되는데 행동으로 안 이어진다" 다. 그래서 화면 맨 위에 지표가 아니라 **문장**을 둔다.
 */
export function leakVerdict(steps: FunnelStep[]): Verdict {
  const drops = steps.slice(1).map((step, index) => {
    const before = steps[index];
    const kept = before.value === 0 ? 0 : step.value / before.value;
    return { from: before.label, to: step.label, kept, lost: before.value - step.value };
  });
  const worst = drops.reduce((a, b) => (a.kept <= b.kept ? a : b));

  // 키는 퍼널 단계 이름(martAdapter standardFunnel)에서 공백을 뺀 것. 단계 이름이 바뀌면 여기도 같이 바꾼다
  const ACTION: Record<string, string> = {
    상세를봄: '목록의 상품 사진과 이름, 빠른 보기 첫 화면을 손보세요',
    장바구니에담음: '가격·용량·담기 버튼을 점검하세요',
    결제로감: '장바구니에서 결제로 가는 길에 막히는 것이 없는지 보세요',
    구매: '결제 단계에서 실패·취소가 나는지 확인하세요',
  };
  const key = worst.to.replace(/\s/g, '');

  return {
    headline: `"${worst.from}" → "${worst.to}" 사이에서 가장 많이 나갑니다`,
    // 단계 값은 사람 수가 아니라 방문 수(세션)다. "명" 으로 적으면 없는 사람 수를 말하게 된다
    reason: `방문 ${fmt.int(worst.lost)}건이 여기서 멈췄고, ${fmt.pct(worst.kept)}만 넘어왔습니다`,
    action: ACTION[key] ?? '이 단계 화면을 다시 살펴보세요',
    sampleSize: steps[0]?.value ?? 0,
  };
}

export function rankInsights(m: BehaviorMetrics): Insight[] {
  const out: Insight[] = [];
  const { contentAttention, segmentMatrix, segmentTopContent, ingredientGap, standardFunnel } = m;

  // ① 콘텐츠: 오래 보지만 안 산다 (lift ≤ 0.8 & 체류 상위 절반)
  const byDwell = [...contentAttention].sort((a, b) => b.avgDwellMs - a.avgDwellMs);
  const half = byDwell.slice(0, Math.ceil(byDwell.length / 2));
  for (const c of half) {
    if (c.conversionLift <= 0.8 && c.sampleSize >= 200) {
      const dev = Math.min(1, (1 - c.conversionLift) / 0.5);
      const why =
        c.kind === 'usage_guide'
          ? '설명이 어렵거나 길 수 있습니다'
          : c.kind.startsWith('ingredient')
            ? '피하는 성분을 보고 돌아섰을 수 있습니다'
            : '살 이유가 잘 안 보였을 수 있습니다';
      out.push({
        id: `content-weak-${c.kind}`,
        origin: 'mine',
        screen: 'content',
        headline: `오래 읽는데 담지 않는 설명: ${c.ko}`,
        reasons: [
          `평균 ${(c.avgDwellMs / 1000).toFixed(0)}초 읽지만 담기는 평균의 ${c.conversionLift.toFixed(1)}배 (${fmt.int(c.sampleSize)}건)`,
          why,
        ],
        action: c.kind === 'usage_guide' ? '단계별 사진과 1회 사용량·횟수를 적어 다시 쓰세요' : `${c.ko}에 시험 결과·같은 피부 리뷰를 덧붙이세요`,
        unit: '상세페이지',
        n: c.sampleSize,
        confidence: conf(c.sampleSize, 2),
        score: dev * Math.log(c.sampleSize),
        beautyNoun: true,
      });
    }
  }
  // ② 콘텐츠: 짧게 보지만 결정에 기여 (lift ≥ 1.3 & 체류 하위 절반)
  const lowHalf = byDwell.slice(Math.ceil(byDwell.length / 2));
  for (const c of lowHalf) {
    if (c.conversionLift >= 1.3 && c.sampleSize >= 200) {
      const dev = Math.min(1, (c.conversionLift - 1) / 1.5);
      out.push({
        id: `content-strong-${c.kind}`,
        origin: 'mine',
        screen: 'content',
        headline: `짧게 읽어도 담기 ${c.conversionLift.toFixed(1)}배: ${c.ko}`,
        reasons: [
          `상세 방문 중 ${fmt.pct(c.viewRate)}만 읽고, 평균 ${(c.avgDwellMs / 1000).toFixed(0)}초로 짧습니다 (${fmt.int(c.sampleSize)}건)`,
          '읽으면 담는데 읽는 고객이 적습니다',
        ],
        action: `${josa(c.ko, '을/를')} 상세페이지 위쪽과 상품 목록에 올리세요`,
        unit: '상세페이지',
        n: c.sampleSize,
        confidence: conf(c.sampleSize, 1),
        score: dev * Math.log(c.sampleSize) * 0.9,
        beautyNoun: true,
      });
    }
  }

  // ③ 고객군: 최고·최저 셀 차 ≥ 10%p (n ≥ 200, 복합성은 톤으로만 서술)
  const cells = segmentMatrix.flatMap((r) => r.cells.map((c) => ({ type: r.type, ...c }))).filter((c) => c.sessions >= 200);
  if (cells.length >= 2) {
    const best = cells.reduce((a, b) => (a.cartRate >= b.cartRate ? a : b));
    const worst = cells.reduce((a, b) => (a.cartRate <= b.cartRate ? a : b));
    const gap = best.cartRate - worst.cartRate;
    if (gap >= 0.1) {
      const name = (c: typeof best) => (c.type === 'combination' ? `복합성 ${TONE_KO[c.tone]}` : `${SKIN_TYPE_KO[c.type]} ${TONE_KO[c.tone]}`);
      const top = segmentTopContent.find((s) => s.type === best.type);
      out.push({
        id: 'segment-gap',
        origin: 'mine',
        screen: 'segments',
        headline: `${name(best)} 고객이 가장 많이 담습니다`,
        reasons: [
          `${name(best)} ${fmt.pct(best.cartRate)} · ${name(worst)} ${fmt.pct(worst.cartRate)} 담았습니다`,
          top ? `${SKIN_TYPE_KO[best.type]} 고객이 가장 오래 읽는 설명: ${top.top}` : '',
        ].filter(Boolean),
        action: `${name(best)} 고객에 맞춰 문구를 쓰고 ${top ? `${top.top} 설명을` : '즐겨 읽는 설명을'} 앞에 두세요`,
        unit: '고객·문구',
        n: Math.min(best.sessions, worst.sessions),
        confidence: conf(Math.min(best.sessions, worst.sessions), 2),
        score: Math.min(1, gap / 0.2) * Math.log(Math.min(best.sessions, worst.sessions)),
        beautyNoun: true,
      });
    }
  }

  // ④ 성분 갭: 관심 상위 10 & 미보유
  const gaps = ingredientGap.filter((g) => g.gap).slice(0, 2);
  if (gaps.length > 0) {
    const n = gaps.reduce((s, g) => s + g.scrapeCount, 0) * 10; // 드래그 수 → 세션 근사
    out.push({
      id: 'ingredient-gap',
      // 성분 관심은 ingredient_weekly_interest — brand 축이 없는 플랫폼 전체 값 (마트 계약 E5)
      origin: 'shared',
      screen: 'ingredients',
      headline: `많이 찾는데 내 상품엔 없는 성분: ${gaps.map((g) => labelKo(g.name)).join('·')}`,
      reasons: gaps.map((g) => `${labelKo(g.name)}: 관심 ${g.rank}위 · ${fmt.int(g.scrapeCount)}번 살펴봄 · 내 상품엔 없음`),
      action: `${josa(labelKo(gaps[0].name), '이/가')} 든 상품을 다음 기획 후보로 두세요`,
      unit: '제품·처방',
      n,
      confidence: n >= 1000 ? '보통' : '낮음',
      score: 0.6 * Math.log(Math.max(2, n)),
      beautyNoun: true,
    });
  }

  // ⑤ 퍼널 누수 (뷰티 명사 없음 → 다른 후보가 없을 때만)
  if (standardFunnel.length >= 2) {
    const leak = leakVerdict(standardFunnel);
    out.push({
      id: 'funnel-leak',
      origin: 'mine',
      screen: 'products',
      headline: leak.headline,
      reasons: [leak.reason],
      action: leak.action,
      unit: '상세페이지',
      n: standardFunnel[0].value,
      confidence: '보통',
      score: 0.3 * Math.log(Math.max(2, standardFunnel[0].value)),
      beautyNoun: false,
    });
  }

  const beauty = out.filter((i) => i.beautyNoun && i.n >= 200).sort((a, b) => b.score - a.score);
  const rest = out.filter((i) => !beauty.includes(i)).sort((a, b) => b.score - a.score);
  return [...beauty, ...rest];
}
