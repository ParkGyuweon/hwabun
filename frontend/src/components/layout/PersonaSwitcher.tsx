import { useMemo, useState } from 'react';
import { humanizeAttribute, skinTypeLabel } from '../../lib/format';
import type { PersonaProfile } from '../../types/persona';

interface PersonaSwitcherProps {
  personas: PersonaProfile[];
  persona: PersonaProfile | null;
  onPersonaChange: (personaId: string) => void;
}

/**
 * 접속 중인 페르소나. 이 실험 사이트에서는 로그인 사용자에 해당한다.
 *
 * 세포라 리뷰 작성자에서 파생한 페르소나가 실제 방문자 역할을 하고,
 * 여기서 고른 값이 모든 로그의 persona_id 가 된다.
 *
 * 최종 데이터셋은 페르소나가 만 단위라 select 하나로는 감당이 안 된다.
 * 지금은 샘플 규모라 목록을 그대로 열지만, 피부 타입 필터와 검색을 먼저 태워
 * 나중에 서버 검색으로 바꿔도 화면 구조가 유지되게 해둔다.
 */
export default function PersonaSwitcher({ personas, persona, onPersonaChange }: PersonaSwitcherProps) {
  const [open, setOpen] = useState(false);
  const [keyword, setKeyword] = useState('');

  /**
   * 검색 축을 피부 타입·톤으로 좁혔다.
   *
   * eye_color / hair_color 는 실제 리뷰어 분포를 살린 값이라 균등하지 않다
   * (brown 이 각각 71%, 42%). 이 두 축으로 찾게 두면 선택지가 한쪽으로 쏠려서
   * 고르는 데 도움이 안 된다. 피부 타입 4종 × 톤 5종은 정확히 균등이다.
   */
  const filtered = useMemo(() => {
    const needle = keyword.trim().toLowerCase();
    if (!needle) return personas;
    return personas.filter((item) =>
      [item.persona_id, item.skin_type, item.skin_tone].join(' ').toLowerCase().includes(needle),
    );
  }, [personas, keyword]);

  return (
    <div className="persona">
      <button
        type="button"
        className="persona__trigger"
        aria-expanded={open}
        data-log-action="persona_switcher_open"
        onClick={() => setOpen((prev) => !prev)}
      >
        <span className="persona__avatar" aria-hidden="true">
          {persona ? persona.persona_id.slice(-2) : '?'}
        </span>
        <span className="persona__label">
          {persona ? (
            <>
              <strong>{skinTypeLabel(persona.skin_type)}</strong>
              <span>{humanizeAttribute(persona.skin_tone)}</span>
            </>
          ) : (
            <strong>페르소나 선택</strong>
          )}
        </span>
      </button>

      {open ? (
        <div className="persona__panel">
          <label className="persona__search">
            <span className="sr-only">페르소나 검색</span>
            <input
              type="search"
              value={keyword}
              placeholder="피부 타입·톤으로 검색"
              onChange={(event) => setKeyword(event.target.value)}
            />
          </label>

          <ul className="persona__list">
            {filtered.map((item) => (
              <li key={item.persona_id}>
                <button
                  type="button"
                  className={item.persona_id === persona?.persona_id ? 'is-active' : ''}
                  onClick={() => {
                    onPersonaChange(item.persona_id);
                    setOpen(false);
                  }}
                >
                  <span className="persona__list-main">
                    {skinTypeLabel(item.skin_type)} · {humanizeAttribute(item.skin_tone)}
                  </span>
                  <span className="persona__list-sub">
                    {item.persona_id} · 리뷰 {item.n_reviews}
                  </span>
                </button>
              </li>
            ))}
          </ul>

          {filtered.length === 0 ? <p className="empty-state">일치하는 페르소나가 없습니다.</p> : null}
        </div>
      ) : null}
    </div>
  );
}
