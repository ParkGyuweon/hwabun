/**
 * 추천 응답 하나 · 서버가 있으면 서버, 없으면 목.
 *
 * 화면은 `recommendation` 만 본다. 어디서 왔는지는 `source` 로 알 수 있고, 로그에는 응답의
 * `recommendation_id`·`model_version`(= 서버 `algorithm`) 이 그대로 실리므로 서버·목이 마트에서 갈린다
 * (목은 `mock-fe-*`).
 *
 * 순서
 *   1. 목을 먼저 만든다 (동기). 화면이 비는 순간이 없다
 *   2. 식별자(회원 accountId 또는 페르소나 id)가 있으면 서버를 부른다. 없으면 부르지 않는다 (계약 §5 · 09-10 합의)
 *   3. 응답이 오면 카탈로그에 있는 상품만 남기고 바꿔 끼운다. 비었거나 실패면 목 그대로
 *
 * 다시 부르는 때: 식별자·축·정책·칸 수가 바뀔 때. 장바구니는 아니다 — 서버는 자기 상태(POST /api/events →
 * Kafka)로 전환 상품을 빼고, 화면은 받은 목록에서 담은 상품을 한 번 더 걸러낸다. 담을 때마다 다시 부르면
 * 추천 줄이 계속 흔들려 노출 귀속이 깨진다.
 */
import { useEffect, useMemo, useState } from 'react';
import { type BuildInput, buildRecommendation } from '../lib/recommendMock';
import { fetchRecommendation } from '../lib/recommendApi';
import type { RecommendResponse } from '../types/recommendation';
import type { MemberProfile } from '../lib/memberProfile';

export type RecommendationSource = 'server' | 'mock';

export interface UseRecommendationInput extends BuildInput {
  /** 회원 accountId 또는 시뮬레이션 페르소나 id. null 이면 서버를 부르지 않는다 */
  identityId: string | null;
  /** 실회원 피부 프로필. 쿼리 4개로 실린다 (AI 회신 2026-09-11). 페르소나 표 id 면 null */
  profile?: MemberProfile | null;
}

export function useRecommendation(input: UseRecommendationInput): { recommendation: RecommendResponse; source: RecommendationSource } {
  const { identityId, products, excluded, axes, heroPolicy, k, bannerSlots, reserved, profile = null } = input;

  const mock = useMemo(() => buildRecommendation(input), [input]);

  const axesKey = axes.join(',');
  const profileKey = profile ? `${profile.skin_type ?? ''}/${profile.skin_tone ?? ''}/${profile.hair_color ?? ''}/${profile.eye_color ?? ''}` : '';
  const key = identityId ? `${identityId}|${k}|${bannerSlots}|${reserved}|${heroPolicy ?? 'top'}|${axesKey}|${profileKey}` : null;
  const [server, setServer] = useState<{ key: string; response: RecommendResponse } | null>(null);

  useEffect(() => {
    if (!key || !identityId) return;
    const controller = new AbortController();
    void fetchRecommendation(
      { personaId: identityId, size: k, bannerSlots, reserved, axes, hero: heroPolicy ?? 'top', profile },
      controller.signal,
    ).then((res) => {
      if (controller.signal.aborted) return;
      if (res) setServer({ key, response: res });
    });
    return () => controller.abort();
    // key 가 입력 전부를 담는다. axes 배열 참조가 바뀌어도 내용이 같으면 다시 부르지 않는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return useMemo(() => {
    const fresh = server && server.key === key ? server.response : null;
    if (!fresh) return { recommendation: mock, source: 'mock' as const };

    // 카탈로그에 없는 상품(등록·동기화 시차)과 담은 상품은 뺀다. 순위(rank)는 서버 값 그대로 둔다 — position 로그가 응답과 같아야 한다
    const known = new Set(products.map((p) => p.product_id));
    const items = fresh.items.filter((it) => known.has(it.product_id) && !excluded.has(it.product_id));
    if (items.length === 0) return { recommendation: mock, source: 'mock' as const };
    const hero = fresh.hero && known.has(fresh.hero.product_id) && !excluded.has(fresh.hero.product_id) ? fresh.hero : null;
    const banners = fresh.banners.filter((b) => known.has(b.product_id) && !excluded.has(b.product_id));
    return { recommendation: { ...fresh, items, hero, banners }, source: 'server' as const };
  }, [server, key, mock, products, excluded]);
}
