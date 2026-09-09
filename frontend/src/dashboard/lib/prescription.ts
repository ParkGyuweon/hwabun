import { labelKo } from '../../lib/formLabels';
import {
  contentAttention,
  fmt,
  frictionByLocation,
  scrapedIngredients,
  segmentTopContent,
  SKIN_TYPE_KO,
  quickExitRate,
  validationBehaviors,
} from './metrics';

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
 * 지금은 규칙 표로 쓴다. 운영에서는 같은 입력을 받아 LLM 이 문장을 쓴다 ·
 * 프롬프트와 입출력 규격은 docs/dashboard/action-prescription-prompt.md 에 있다.
 * 그 프롬프트의 출력 스키마가 이 파일의 `Prescription` 과 같은 모양이다.
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

const byKind = new Map(contentAttention.map((c) => [c.kind, c]));
const dwellSec = (kind: string) => Math.round((byKind.get(kind)?.avgDwellMs ?? 0) / 1000);
const viewPct = (kind: string) => fmt.pct(byKind.get(kind)?.viewRate ?? 0);
const liftOf = (kind: string) => (byKind.get(kind)?.conversionLift ?? 1).toFixed(1);

const drag3 = scrapedIngredients.slice(0, 3).map((i) => labelKo(i.name));
const behavior = (event: string) => validationBehaviors.find((v) => v.event === event);
const friction = (where: string) => frictionByLocation.find((f) => f.where === where);
const topFor = (type: string) => segmentTopContent.find((s) => s.type === type);

/** 고객군 화면에서 그 콘텐츠를 가장 오래 보는 피부 타입을 찾는다 */
function segmentBasis(contentKo: string): Basis | null {
  const hit = segmentTopContent.find((s) => s.top === contentKo);
  if (!hit) return null;
  return {
    from: '누가 사나',
    text: `${SKIN_TYPE_KO[hit.type]} 고객이 상세페이지에서 가장 오래 보는 글이 ${contentKo}입니다. 이 고객군 체류 시간의 ${fmt.pct(hit.dwellShare)}를 여기서 씁니다.`,
  };
}

const expand = behavior('ingredient_view_mode_change');
const skinFilter = behavior('review_filter_apply');
const accordion = behavior('accordion_toggle');
const backtrack = friction('성분 목록');
const deadClick = friction('상품 이미지');
const hesitate = friction('담기 버튼');

/**
 * 콘텐츠별 처방.
 *
 * 손볼 것·올릴 것에만 처방을 둔다. 그대로 둘 것에 지시를 붙이면 할 일이 열 개가 되고,
 * 열 개는 하나도 안 하게 된다.
 */
export const PRESCRIPTION: Record<string, Prescription> = {
  clinical_claim: {
    how: `임상 결과를 사용자 리뷰 위, 성분 목록 바로 아래로 옮기세요. 줄글 대신 시험 대상 인원·기간·측정 항목·결과를 4줄 표로 바꾸고, 표 아래에 시험 기관명을 한 줄 적으세요.`,
    basis: [
      {
        from: '무엇을 보고 사나',
        text: `이 글을 본 사람의 담기율이 평균의 ${liftOf('clinical_claim')}배인데, 상세페이지를 연 사람 중 ${viewPct('clinical_claim')}만 여기까지 내려옵니다. 안 보여서 못 먹히고 있습니다.`,
      },
      segmentBasis('임상 결과') ?? {
        from: '누가 사나',
        text: '고객군별 체류 구성에서 임상 결과 비중이 가장 큽니다.',
      },
      {
        from: '무엇을 보고 사나',
        text: `전성분을 펼쳐 본 방문의 담기율은 ${fmt.pct(expand?.cartRateWith ?? 0)}, 안 펼친 방문은 ${fmt.pct(expand?.cartRateWithout ?? 0)}입니다. 근거를 찾아 읽는 방문이 담습니다.`,
      },
    ],
    verify: `열람률 ${viewPct('clinical_claim')} → 50%. 올린 뒤에도 이 글을 본 방문의 담기율이 2.0배 이상이면 위치가 맞았다는 뜻입니다. 열람률만 오르고 담기율이 1.5배 아래로 떨어지면 관심 없는 사람에게도 보인 것이니 되돌리세요.`,
  },

  ingredient_callout: {
    how: `성분 특징을 전성분 목록 위로 올리고, 고객이 가장 많이 드래그한 성분 ${drag3.length}개(${drag3.join('·')})를 맨 앞 카드로 세우세요. 성분마다 무엇인지 한 줄, 이 제품에 왜 넣었는지 한 줄이면 됩니다.`,
    basis: [
      {
        from: '무엇을 보고 사나',
        text: `이 글을 본 사람의 담기율이 평균의 ${liftOf('ingredient_callout')}배인데, 열람은 ${viewPct('ingredient_callout')}에 그칩니다.`,
      },
      {
        from: '고객이 찾는 성분',
        text: `고객이 상세페이지에서 직접 드래그해 찾아본 성분 상위 3개가 ${drag3.join('·')}입니다. 이 이름부터 설명하면 찾는 수고가 사라집니다.`,
      },
      {
        from: '막히는 곳',
        text: `성분 목록 구간에서 위로 다시 올려 읽은 기록이 ${fmt.int(backtrack?.count ?? 0)}건입니다. 한 번 읽고 이해가 안 됐다는 뜻일 수 있습니다.`,
      },
    ],
    verify: `열람률 ${viewPct('ingredient_callout')} → 55%, 성분 목록 구간의 되돌아 읽기 ${fmt.int(backtrack?.count ?? 0)}건 → 300건 아래. 두 값이 같이 움직이면 설명이 통한 것입니다.`,
  },

  usage_guide: {
    how: `사용법을 줄글에서 아침·저녁 2열 표로 바꾸세요. 한 칸에 순서 번호, 한 번에 쓰는 양, 다른 제품과 겹칠 때 무엇을 먼저 쓰는지 세 줄만 넣으세요. ${dwellSec('usage_guide')}초는 읽을 시간이 아니라 찾는 시간입니다.`,
    basis: [
      {
        from: '무엇을 보고 사나',
        text: `${dwellSec('usage_guide')}초나 읽는데 본 사람의 담기율이 평균의 ${liftOf('usage_guide')}배입니다. 읽히긴 하는데 결정으로 이어지지 않습니다.`,
      },
      {
        from: '무엇을 보고 사나',
        text: `접힌 정보를 펼친 방문의 담기율은 ${fmt.pct(accordion?.cartRateWith ?? 0)}, 안 펼친 방문은 ${fmt.pct(accordion?.cartRateWithout ?? 0)}입니다. 펼치는 수고를 덜어 주면 더 많은 방문이 이 정보를 봅니다.`,
      },
      {
        from: '막히는 곳',
        text: `담기 버튼 위에서 머뭇거린 기록이 ${fmt.int(hesitate?.count ?? 0)}건, 평균 2.4초입니다. 마지막까지 안 풀린 질문이 남아 있다는 신호입니다.`,
      },
    ],
    verify: `평균 읽는 시간 ${dwellSec('usage_guide')}초 → 8초, 담기율 ${liftOf('usage_guide')}배 → 1.0배 이상. 시간이 줄고 담기율이 오르면 찾기 쉬워진 것입니다. 시간만 줄고 담기율이 그대로면 내용을 덜어낸 것이니 되돌리세요.`,
  },

  what_else: {
    how: `추가 설명 칸을 빼고, 남길 내용은 성분 특징이나 사용법 안으로 옮기세요. 열 종 중 담기율이 가장 낮은 칸이고, 여기를 지우면 위 글들이 그만큼 위로 올라옵니다.`,
    basis: [
      {
        from: '무엇을 보고 사나',
        text: `본 사람의 담기율이 평균의 ${liftOf('what_else')}배로 열 종 중 가장 낮고, 열람도 ${viewPct('what_else')}에 그칩니다.`,
      },
      {
        from: '무엇을 보고 사나',
        text: `같은 자리에 놓을 수 있는 임상 결과는 담기율이 ${liftOf('clinical_claim')}배입니다. 자리를 바꾸면 그 차이가 그대로 옵니다.`,
      },
      {
        from: '막히는 곳',
        text: `상세페이지를 열고 3초 안에 나간 방문이 ${fmt.pct(quickExitRate)}입니다. 페이지가 길수록 끝까지 내려오는 사람이 줄어드니, 담기율 낮은 칸부터 덜어내는 것이 순서입니다.`,
      },
    ],
    verify: `뺀 뒤 상세페이지 전체 평균 읽는 시간이 줄지 않아야 합니다. 줄면 필요한 내용을 지운 것입니다. 임상 결과 열람률이 함께 오르면 자리 교체가 통한 것입니다.`,
  },

  user_review: {
    how: `리뷰 위에 "내 피부 타입만 보기" 버튼을 기본으로 켜 두세요. 지금은 고객이 직접 눌러야 합니다.`,
    basis: [
      {
        from: '무엇을 보고 사나',
        text: `내 피부 타입 리뷰만 본 방문의 담기율은 ${fmt.pct(skinFilter?.cartRateWith ?? 0)}, 안 본 방문은 ${fmt.pct(skinFilter?.cartRateWithout ?? 0)}입니다. 그런데 실제로 누른 방문은 ${fmt.pct(skinFilter?.doneRate ?? 0)}뿐입니다.`,
      },
      {
        from: '누가 사나',
        text: `리뷰 필터를 쓴 방문 중 63%가 자기 피부 타입을 골랐습니다. 고객이 원하는 기본값이 이미 나와 있습니다.`,
      },
    ],
    verify: `필터 사용률 ${fmt.pct(skinFilter?.doneRate ?? 0)} → 40%. 리뷰 구간 이탈이 함께 줄어야 합니다.`,
  },

  ingredient_list: {
    how: `전성분을 펼친 상태로 두거나, 앞 5개를 접힌 채로도 보이게 하세요. 지금은 ${fmt.pct(expand?.doneRate ?? 0)}만 펼쳐 봅니다.`,
    basis: [
      {
        from: '무엇을 보고 사나',
        text: `펼쳐 본 방문의 담기율은 ${fmt.pct(expand?.cartRateWith ?? 0)}, 안 펼친 방문은 ${fmt.pct(expand?.cartRateWithout ?? 0)}입니다. 두 배 넘게 벌어집니다.`,
      },
      {
        from: '막히는 곳',
        text: `이 구간에서 위로 다시 올려 읽은 기록이 ${fmt.int(backtrack?.count ?? 0)}건입니다.`,
      },
    ],
    verify: `펼쳐 보기 실행률 ${fmt.pct(expand?.doneRate ?? 0)} → 40%. 담기율 차이가 그대로 유지되는지 보세요.`,
  },

  product_image: {
    how: `상품 이미지를 누르면 확대되게 하세요. 지금은 눌러도 아무 일이 없습니다.`,
    basis: [
      {
        from: '막히는 곳',
        text: `상품 이미지에서 눌러도 아무 일이 없었던 기록이 ${fmt.int(deadClick?.count ?? 0)}건입니다. 열 종 중 가장 많이 보이는 글(${viewPct('product_image')})에서 벌어지는 일입니다.`,
      },
      {
        from: '무엇을 보고 사나',
        text: `${dwellSec('product_image')}초만 보고 넘어갑니다. 확대가 막혀 있어 더 볼 수 없었을 가능성이 있습니다.`,
      },
    ],
    verify: `눌러도 아무 일이 없던 기록 ${fmt.int(deadClick?.count ?? 0)}건 → 100건 아래. 이미지 구간 체류가 함께 늘어야 합니다.`,
  },
};

/** 기본 처방. 규칙에 걸리지 않은 콘텐츠에는 지시를 만들지 않는다 */
export function prescriptionFor(kind: string): Prescription | null {
  return PRESCRIPTION[kind] ?? null;
}

/** 아직 처방 문장이 없는 콘텐츠. 화면에서 솔직히 밝힌다 */
export function hasPrescription(kind: string): boolean {
  return kind in PRESCRIPTION;
}

/** 고객군 화면에서 쓰는 도움 함수. 처방과 같은 근거를 재사용한다 */
export { topFor as segmentTopFor };
