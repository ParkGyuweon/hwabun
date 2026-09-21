import { labelKo } from '../../lib/formLabels';
import type { BehaviorMetrics } from './behavior';
import type { ContentAttention } from './metrics';
import { SKIN_TYPE_KO, fmt } from './metrics';
import { josa } from '../../lib/format';

/**
 * 처방 · "위로 올리세요" 다음 문장.
 *
 * 동작 이름만 주면 사장님이 다시 묻는다 · **무엇을 어떻게.** 그 답을 화면이 낸다.
 *
 * 처방은 한 화면의 숫자만으로 못 쓴다. "임상 결과를 올려라" 는 이 화면의 담기율에서
 * 나오지만, "표 3줄로 바꿔라" 는 고객군 화면의 체류 구성과 막히는 곳 화면의 되돌아
 * 읽기에서 나온다. 그래서 처방마다 **근거를 어느 화면에서 가져왔는지**(`from`) 를
 * 함께 들고 다니고, 화면에서 펼쳐 볼 수 있게 한다. 근거 없는 지시는 넣지 않는다.
 *
 * 두 경로가 있다.
 *   - **AI 서버** `POST /api/prescription` (batch/serving, 규격 v0.3) · prescriptionApi.ts 가 부른다
 *   - **규칙 표** 이 파일. 서버가 없거나 거부하면 이걸 쓴다. 입력은 서버와 같은 행동 지표 묶음이다
 *
 * 규칙 표는 모듈 상수가 아니라 **함수**다. 마트가 붙으면 숫자가 브랜드·기간마다 달라지므로
 * 그때의 지표 묶음(BehaviorMetrics)을 받아 문장을 만든다.
 *
 * 문구 규칙 (docs/dashboard/ai-insight-rules.md §4-3): 효능을 단정하지 않는다.
 * "주름이 개선됩니다" 가 아니라 "시험 대상 인원과 기간을 적으세요" 처럼 **브랜드가
 * 할 일**만 쓴다. 화장품법 제13·14조 금지 표현은 처방 문장에 등장할 수 없다.
 */

export interface Basis {
  /** 이 근거를 가져온 화면. 사장님이 직접 가서 확인할 수 있어야 한다 */
  from: string;
  text: string;
}

export interface Prescription {
  /** 무엇을 어떻게. 명령 한 문장. 위치·형식·개수까지 적는다 */
  how: string;
  /** 처방을 지지하는 근거. 서로 다른 화면에서 최소 둘 */
  basis: Basis[];
  /** 무엇이 얼마나 바뀌면 성공인가. 다음 주에 이 줄로 채점한다 */
  verify: string;
}

/**
 * AI 파트가 내려 주는 응답 봉투 (규격 v0.3 §8 · contracts/prescription-api-spec.md §3).
 *
 * 자동 거부는 생성하는 쪽이 건다. 입력 JSON 을 들고 있어야 "없는 숫자" 를 대조할 수
 * 있기 때문이다. 그래서 프론트는 `prescription` 이 null 이면 규칙 표로 물러난다.
 */
export interface PrescriptionEnvelope {
  content_kind: string;
  verb: 'up' | 'fix';
  brand?: string;
  prescription: Prescription | null;
  /** 거부 사유 코드. 비어 있지 않으면 prescription 은 null */
  rejected_by: string[];
  /** 실증자료가 필요한 표현. 있으면 화면에 꼬리표를 붙인다 */
  needs_evidence: string[];
  model: string;
  prompt_version: string;
  input_hash: string;
  generated_at: string;
  cached?: boolean;
}

/** 봉투에서 처방만 꺼낸다 */
export function fromEnvelope(envelope: PrescriptionEnvelope): Prescription | null {
  if (envelope.rejected_by.length > 0) return null;
  return envelope.prescription;
}

/**
 * 옮길 위치를 정한다. AI 가 아니라 여기서 정한다 (규격 v0.3 §2-1).
 *
 * AI 파트 실측 회신: 모델은 매번 "맨 위로" 를 고른다. 규칙상 틀리지 않지만 처방이
 * 단조로워지고, 더 잘 먹히는 칸을 아래로 밀어낸다. 위치는 문장 감각이 아니라 규칙
 * 문제라서 프론트가 계산해 입력으로 넘긴다.
 *
 *   더 잘 먹히는 칸은 그대로 위에 두고, 그 바로 아래에 넣는다.
 *   = 담기율 배수가 대상보다 높은 칸 중 **가장 낮은** 칸의 바로 아래
 *
 * 상품별 블록 노출 순서 마트가 없어서(§9 요청 4번) 지금은 담기율 순서로 대신한다.
 */
export function insertAfter(kind: string, content: ContentAttention[]): string | null {
  const target = content.find((c) => c.kind === kind);
  if (!target) return null;
  const better = content.filter((c) => c.conversionLift > target.conversionLift).sort((a, b) => a.conversionLift - b.conversionLift);
  return better[0]?.ko ?? null;
}

/**
 * 콘텐츠별 처방 표를 지표 묶음에서 만든다.
 *
 * 손볼 것·올릴 것에만 처방을 둔다. 그대로 둘 것에 지시를 붙이면 할 일이 열 개가 되고,
 * 열 개는 하나도 안 하게 된다.
 */
export function buildPrescriptions(m: BehaviorMetrics): Record<string, Prescription> {
  const byKind = new Map(m.contentAttention.map((c) => [c.kind, c]));
  const dwellSec = (kind: string) => Math.round((byKind.get(kind)?.avgDwellMs ?? 0) / 1000);
  const viewPct = (kind: string) => fmt.pct(byKind.get(kind)?.viewRate ?? 0);
  const liftOf = (kind: string) => (byKind.get(kind)?.conversionLift ?? 1).toFixed(1);
  const after = (kind: string) => insertAfter(kind, m.contentAttention) ?? '맨 위';

  const drag3 = m.scrapedIngredients.slice(0, 3).map((i) => labelKo(i.name));
  const behavior = (event: string) => m.validationBehaviors.find((v) => v.event === event);
  const friction = (where: string) => m.frictionByLocation.find((f) => f.where === where);

  /** 고객군 화면에서 그 콘텐츠를 가장 오래 보는 피부 타입을 찾는다 */
  const segmentBasis = (contentKo: string): Basis | null => {
    const hit = m.segmentTopContent.find((s) => s.top === contentKo);
    if (!hit) return null;
    return {
      from: '누가 사나',
      text: `${SKIN_TYPE_KO[hit.type]} 고객이 가장 오래 보는 글 · 읽는 시간의 ${fmt.pct(hit.dwellShare)}`,
    };
  };

  const expand = behavior('ingredient_view_mode_change');
  const skinFilter = behavior('review_filter_apply');
  const accordion = behavior('accordion_toggle');
  const backtrack = friction('성분 목록');
  const deadClick = friction('상품 이미지');
  const hesitate = friction('담기 버튼');

  return {
    clinical_claim: {
      how: `임상 결과를 ${after('clinical_claim')} 바로 아래로 옮기고, 인원·기간·항목·결과 4줄 표로 바꾸세요.`,
      basis: [
        {
          from: '무엇을 보고 사나',
          text: `평균의 ${liftOf('clinical_claim')}배 담는데, 본 사람은 ${viewPct('clinical_claim')}뿐`,
        },
        segmentBasis('임상 결과') ?? {
          from: '누가 사나',
          text: '고객군별 읽는 시간에서 임상 결과가 가장 큼',
        },
        {
          from: '무엇을 보고 사나',
          text: `전성분 펼친 방문 담기 ${fmt.pct(expand?.cartRateWith ?? 0)} · 안 펼친 방문 ${fmt.pct(expand?.cartRateWithout ?? 0)}`,
        },
      ],
      verify: `본 비율 ${viewPct('clinical_claim')} → 50%, 담기 배수 2.0배 유지`,
    },

    ingredient_callout: {
      how: `성분 특징을 ${after('ingredient_callout')} 바로 아래로 옮기고, ${josa(drag3.join('·'), '을/를')} 맨 앞 카드로 세우세요.`,
      basis: [
        {
          from: '무엇을 보고 사나',
          text: `평균의 ${liftOf('ingredient_callout')}배 담는데, 본 사람은 ${viewPct('ingredient_callout')}뿐`,
        },
        {
          from: '고객이 찾는 성분',
          text: `가장 많이 드래그한 성분: ${drag3.join('·')}`,
        },
        {
          from: '막히는 곳',
          text: `성분 목록에서 되돌아가 다시 읽음 ${fmt.int(backtrack?.count ?? 0)}건`,
        },
      ],
      verify: `본 비율 ${viewPct('ingredient_callout')} → 55%, 되돌아 읽기 ${fmt.int(backtrack?.count ?? 0)}건 → 300건 아래`,
    },

    usage_guide: {
      how: `사용법을 아침·저녁 2열 표로 바꾸세요. 순서·양·겹칠 때 먼저 쓸 것, 세 줄만.`,
      basis: [
        {
          from: '무엇을 보고 사나',
          text: `${dwellSec('usage_guide')}초나 읽는데 담기는 평균의 ${liftOf('usage_guide')}배`,
        },
        {
          from: '무엇을 보고 사나',
          text: `접힌 정보 펼친 방문 담기 ${fmt.pct(accordion?.cartRateWith ?? 0)} · 안 펼친 방문 ${fmt.pct(accordion?.cartRateWithout ?? 0)}`,
        },
        {
          from: '막히는 곳',
          text: `담기 버튼 위에서 머뭇거림 ${fmt.int(hesitate?.count ?? 0)}건`,
        },
      ],
      verify: `읽는 시간 ${dwellSec('usage_guide')}초 → 8초, 담기 ${liftOf('usage_guide')}배 → 1.0배 이상`,
    },

    what_else: {
      how: `추가 설명 칸을 빼고, 남길 내용은 성분 특징·사용법 안으로 옮기세요.`,
      basis: [
        {
          from: '무엇을 보고 사나',
          text: `담기 평균의 ${liftOf('what_else')}배로 열 종 중 최저 · 본 사람 ${viewPct('what_else')}`,
        },
        {
          from: '무엇을 보고 사나',
          text: `같은 자리에 올 임상 결과는 ${liftOf('clinical_claim')}배`,
        },
        {
          from: '막히는 곳',
          text: `3초 안에 나간 방문 ${fmt.pct(m.quickExitRate)}`,
        },
      ],
      verify: `전체 읽는 시간 유지, 임상 결과 본 비율 상승`,
    },

    user_review: {
      how: `리뷰 위 "내 피부 타입만 보기"를 기본으로 켜 두세요.`,
      basis: [
        {
          from: '무엇을 보고 사나',
          text: `걸러 본 방문 담기 ${fmt.pct(skinFilter?.cartRateWith ?? 0)} · 안 그런 방문 ${fmt.pct(skinFilter?.cartRateWithout ?? 0)} · 누른 방문 ${fmt.pct(skinFilter?.doneRate ?? 0)}`,
        },
        {
          from: '누가 사나',
          text: `걸러 본 방문 중 ${fmt.pct(m.sameSkinFilterRate, 0)}가 자기 피부 타입 선택`,
        },
      ],
      verify: `버튼 누른 방문 ${fmt.pct(skinFilter?.doneRate ?? 0)} → 40%`,
    },

    ingredient_list: {
      how: `전성분을 펼친 상태로 두거나 앞 5개를 미리 보이게 하세요. 지금 펼침 ${fmt.pct(expand?.doneRate ?? 0)}.`,
      basis: [
        {
          from: '무엇을 보고 사나',
          text: `펼친 방문 담기 ${fmt.pct(expand?.cartRateWith ?? 0)} · 안 펼친 방문 ${fmt.pct(expand?.cartRateWithout ?? 0)}`,
        },
        {
          from: '막히는 곳',
          text: `이 구간 되돌아가 다시 읽음 ${fmt.int(backtrack?.count ?? 0)}건`,
        },
      ],
      verify: `펼친 방문 ${fmt.pct(expand?.doneRate ?? 0)} → 40%`,
    },

    product_image: {
      how: `상품 이미지를 누르면 확대되게 하세요. 지금은 눌러도 반응이 없습니다.`,
      basis: [
        {
          from: '막히는 곳',
          text: `이미지에서 눌러도 반응 없음 ${fmt.int(deadClick?.count ?? 0)}건 · 본 비율 ${viewPct('product_image')}`,
        },
        {
          from: '무엇을 보고 사나',
          text: `${dwellSec('product_image')}초만 보고 넘어감`,
        },
      ],
      verify: `반응 없음 ${fmt.int(deadClick?.count ?? 0)}건 → 100건 아래`,
    },
  };
}

/** 규칙 표 처방 하나. 규칙에 걸리지 않은 콘텐츠에는 지시를 만들지 않는다 */
export function prescriptionFor(kind: string, m: BehaviorMetrics): Prescription | null {
  return buildPrescriptions(m)[kind] ?? null;
}
