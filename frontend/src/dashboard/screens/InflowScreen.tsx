import { useEffect, useState } from 'react';
import { Kpi, LineChart, Panel } from '../components';
import { fetchCrossBrand } from '../lib/martApi';
import type { CrossBrandPayload } from '../lib/martApi';
import { fmt } from '../lib/metrics';

/**
 * 시장 · 다른 브랜드에서 넘어온 고객 (GET /api/seller/dashboard/cross-brand, 2026-09-28).
 *
 * 다른 브랜드 상품을 보던 고객이 추천 카드·배너를 타고 우리 상품으로 넘어온 방문이다. 분모는 우리 브랜드를 본 방문.
 *
 * **사람 수가 아니라 방문 수다.** 서버가 날짜별 방문을 기간 동안 더하므로 여러 날 들른 고객은 날마다 따로 세진다
 * (마트 grain 그대로 · 다른 화면의 방문 지표와 같은 규칙). "고객 N명" 으로 읽히면 실제보다 커 보여서, 칸 이름과
 * 표 옆에 "방문" 을 드러낸다 (2026-09-28 데이터 파트 은솔님).
 * DW 테이블(cross_brand_daily)이 생기기 전에는 서버가 `summary: null` 로 답한다 — 에러가 아니라 "아직 집계 전" 이고,
 * 화면은 그 한 줄만 적는다. 테이블이 생기면 이 화면을 고치지 않아도 채워진다.
 */
export default function InflowScreen({ brandId, days }: { brandId: string | null; days: number }) {
  // undefined = 받는 중, null = 못 받음
  const [data, setData] = useState<CrossBrandPayload | null | undefined>(undefined);
  useEffect(() => {
    if (!brandId) {
      setData(null);
      return;
    }
    let alive = true;
    setData(undefined);
    void fetchCrossBrand({ brandId, days }).then((d) => {
      if (alive) setData(d);
    });
    return () => {
      alive = false;
    };
  }, [brandId, days]);

  const s = data?.summary ?? null;

  // 값이 없으면 빈 칸 셋을 늘어놓지 않고 한 줄로 끝낸다
  if (!s) {
    return (
      <Panel title="다른 브랜드에서 넘어온 방문" source="none">
        <p className="note">
          {data === undefined
            ? '불러오는 중입니다'
            : data === null
              ? '불러오지 못했습니다. 잠시 뒤 다시 열어 주세요'
              : '아직 집계 전입니다. 다른 브랜드를 보던 고객이 추천·배너로 넘어오면 여기에 쌓입니다'}
        </p>
      </Panel>
    );
  }

  return (
    <div className="stack">
      <div className="grid grid--kpi">
        <Kpi
          label="다른 브랜드에서 넘어온 방문"
          value={s.cross_brand_entry_rate != null ? fmt.pct(s.cross_brand_entry_rate) : '-'}
          sub={`우리 상품을 본 방문 ${fmt.int(s.brand_view_sessions)}건 중 ${fmt.int(s.cross_brand_entry_sessions)}건`}
          source="real"
        />
        <Kpi
          label="추천 카드로 넘어옴"
          value={s.recommendation_share_of_cross_brand_entries != null ? fmt.pct(s.recommendation_share_of_cross_brand_entries) : '-'}
          sub={`넘어온 방문 중 · ${fmt.int(s.recommendation_cross_brand_entry_sessions)}건`}
          source="real"
        />
        <Kpi
          label="배너로 넘어옴"
          value={s.banner_share_of_cross_brand_entries != null ? fmt.pct(s.banner_share_of_cross_brand_entries) : '-'}
          sub={`넘어온 방문 중 · ${fmt.int(s.banner_cross_brand_entry_sessions)}건`}
          source="real"
        />
      </div>

      <Panel title={`날짜별 넘어온 방문 · 최근 ${days}일`} source="real" aside="사람 수가 아닌 방문 수 · 여러 날 들르면 날마다 셉니다">
        <LineChart points={(data?.daily ?? []).map((d) => ({ label: d.event_date_kst.slice(5).replace('-', '/'), value: d.cross_brand_entry_sessions }))}
          label="날짜별 다른 브랜드에서 넘어온 방문 수 변화"
          emptyText="아직 넘어온 방문이 없습니다"
        />
      </Panel>
    </div>
  );
}
