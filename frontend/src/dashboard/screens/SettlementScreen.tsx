import { useEffect, useMemo, useState } from 'react';
import { Kpi, Panel } from '../components';
import { fmt } from '../lib/metrics';
import { fetchSettlements, generateSettlement } from '../../lib/shopApi';
import type { Settlement } from '../../lib/shopApi';

/**
 * 정산 (기획 §5 "월 단위 정산 · 수수료 0%").
 *
 * 주문 화면처럼 **쇼핑몰 원장**을 읽는다. 마트를 거치지 않는다.
 * 서버가 매일 02:00(KST) 에 이번 달 정산을 만들고, 결제 완료 품목을 그 달 정산에 더한다. 완료 처리는 운영자가
 * 한다 — 브랜드가 스스로 "받았다" 로 바꿀 수 없다. 여기서 할 수 있는 일은 **지금 바로 다시 세기** 하나다.
 *
 * 수수료는 0% 라서 총 판매액과 정산액이 같다. 그래도 두 칸을 다 적는다 — 수수료가 생기면 여기서 갈린다.
 * 값이 없으면 0 과 "-" 다. 모의로 채우지 않는다.
 */
export default function SettlementScreen({ brandId }: { brandId: string | null }) {
  const [rows, setRows] = useState<Settlement[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const thisMonth = useMemo(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  }, []);

  const load = async (id: string) => {
    const list = await fetchSettlements(id);
    if (list === null) setFailed(true);
    else {
      setFailed(false);
      setRows(list);
    }
  };

  useEffect(() => {
    if (!brandId) return;
    let alive = true;
    setRows(null);
    setFailed(false);
    void fetchSettlements(brandId).then((list) => {
      if (!alive) return;
      if (list === null) setFailed(true);
      else setRows(list);
    });
    return () => {
      alive = false;
    };
  }, [brandId]);

  const totals = useMemo(() => {
    const list = rows ?? [];
    const current = list.find((s) => s.settlement_month.slice(0, 7) === thisMonth) ?? null;
    const pending = list.filter((s) => s.status === 'PENDING').reduce((sum, s) => sum + s.net_amount, 0);
    const completed = list.filter((s) => s.status === 'COMPLETED').reduce((sum, s) => sum + s.net_amount, 0);
    const lastCompleted = list.find((s) => s.status === 'COMPLETED') ?? null;
    return { current, pending, completed, lastCompleted };
  }, [rows, thisMonth]);

  const won = (v: number) => `${fmt.int(v)}원`;
  const monthKo = (ym: string) => {
    const [y, m] = ym.slice(0, 7).split('-');
    return `${y}년 ${Number(m)}월`;
  };

  const recount = async () => {
    if (!brandId || busy) return;
    setBusy(true);
    setNotice(null);
    const r = await generateSettlement(brandId, thisMonth);
    if (r.kind === 'ok') {
      setNotice(`${monthKo(thisMonth)} 정산을 다시 셌습니다 · ${won(r.netAmount)}`);
      await load(brandId);
    } else if (r.kind === 'completed') {
      setNotice(`${monthKo(thisMonth)} 정산은 이미 지급 완료`);
    } else {
      setNotice('다시 세지 못했습니다. 다시 눌러 주세요');
    }
    setBusy(false);
  };

  if (!brandId) {
    return <Panel title="정산" source="real"><p className="note">판매자로 로그인해 주세요</p></Panel>;
  }
  if (failed) {
    return (
      <Panel title="정산" source="real">
        <p className="note">불러오지 못했습니다. 다시 열어 주세요</p>
      </Panel>
    );
  }
  if (rows === null) {
    return <Panel title="정산" source="real" aside="불러오는 중"><p className="note">불러오는 중</p></Panel>;
  }

  return (
    <div className="stack">
      <div className="grid grid--kpi">
        <Kpi
          label={`${monthKo(thisMonth)} 정산 예정`}
          value={totals.current ? won(totals.current.net_amount) : '아직 없음'}
          sub={
            totals.current
              ? totals.current.status === 'COMPLETED'
                ? '지급 완료'
                : '매일 새벽 2시 갱신'
              : '결제 없음 또는 새벽 2시 정산 전'
          }
          source="real"
        />
        <Kpi
          label="받을 돈 (지급 대기)"
          value={won(totals.pending)}
          sub={totals.pending === 0 ? '지급 대기 없음' : '지급되면 여기서 빠짐'}
          source="real"
        />
        <Kpi
          label="받은 돈 (지급 완료)"
          value={won(totals.completed)}
          sub={totals.lastCompleted ? `마지막 지급 ${monthKo(totals.lastCompleted.settlement_month)}분` : '지급 완료 없음'}
          source="real"
        />
        <Kpi label="플랫폼 수수료" value="0%" sub="판매액 = 정산액" source="real" />
      </div>

      <Panel
        title="월별 정산"
        source="real"
        aside={
          <div className="settle__actions">
            <span>{rows.length === 0 ? '0개월' : `${rows.length}개월`}</span>
            <button type="button" className="fbx-btn" onClick={recount} disabled={busy} aria-busy={busy}>
              {busy ? '다시 세는 중' : '이번 달 다시 세기'}
            </button>
          </div>
        }
      >
        {notice ? <p className="note settle__notice" role="status">{notice}</p> : null}
        {rows.length === 0 ? (
          <p className="note">아직 정산이 없습니다. 위 버튼으로 바로 셀 수 있습니다</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>정산 월</th>
                <th title="결제 완료 주문의 내 상품 금액 합 · 취소·환불은 아직 빼지 않음">총 판매액</th>
                <th>수수료</th>
                <th>받을 금액</th>
                <th>지급 상태</th>
                <th>지급일</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.settlement_id}>
                  <td>{monthKo(s.settlement_month)}</td>
                  <td>{won(s.gross_amount)}</td>
                  <td>{won(s.fee_amount)}</td>
                  <td>
                    <strong>{won(s.net_amount)}</strong>
                  </td>
                  <td>
                    <span className={`settle__status settle__status--${s.status.toLowerCase()}`}>
                      {s.status === 'COMPLETED' ? '지급 완료' : '지급 대기'}
                    </span>
                  </td>
                  <td>{s.completed_at ? s.completed_at.slice(0, 10) : '지급 전'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
