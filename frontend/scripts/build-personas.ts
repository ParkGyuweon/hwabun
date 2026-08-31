/**
 * 페르소나 목 데이터를 만든다.
 *
 * 입력  simulator/personas/data/personas_100_agent.json  인터랙티브 전용 100명
 * 출력  src/mocks/personas.sample.json
 *
 * 이 사이트에는 로그인이 없다. **페르소나 전환기가 로그인**이고, 여기서 고른
 * `persona_id` 가 모든 로그에 실린다. 그래서 데이터 파트가 만든 페르소나 표와
 * **같은 ID 체계**를 써야 한다. 예전에는 리뷰 작성자에서 파생시켜 `author_id`
 * (예: "5492222312") 를 실었는데, 그 값은 페르소나 표에 없어서 조인이 안 됐다.
 *
 * PA / PC 대역이 나뉘어 있다.
 *   PA00001~PA00100   인터랙티브 전용. **합성 로그를 만들지 않는다**
 *   PC00001~PC09900   부하·분포 검증용. 1인당 약 590건의 합성 로그가 이미 있다
 *
 * PC 를 화면에 올리면 안 된다. 사람이 눌러 만든 10여 건이 이미 쌓인 590건에
 * 묻혀서, "내가 누른 대로 추천이 바뀐다" 를 보여줄 수 없다.
 * PA 는 피부 타입 4종 × 톤 5종이 정확히 균등이라 어떤 조합을 골라도 시연이 된다.
 * PC 파일은 52MB 라 애초에 번들에 넣을 수도 없다.
 *
 *   npx tsx scripts/build-personas.ts
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');

const SOURCE = 'personas_100_agent.json';

/** 원본에는 샘플링 내부값과 리뷰 이력까지 들어 있다. 화면이 쓰는 것만 추린다 */
interface SourcePersona {
  persona_id: string;
  skin_type: string;
  skin_tone: string;
  eye_color: string;
  hair_color: string;
  n_reviews: number;
}

const parsed = JSON.parse(
  readFileSync(join(root, 'simulator', 'personas', 'data', SOURCE), 'utf8'),
) as SourcePersona[] | Record<string, SourcePersona[]>;

const source = Array.isArray(parsed)
  ? parsed
  : (Object.values(parsed)[0] as SourcePersona[]);

/**
 * `reviews[]` 는 통째로 버린다.
 *
 * 화면이 안 쓰는데 100명치를 담으면 목 파일이 0.5MB 가 된다. 체류 시간을 재는
 * 페이지에서 로드가 느려지면 그게 측정값에 섞인다.
 * 원본 파일은 그대로 둔다. 추천 API 가 "리뷰 쓴 상품 = 이미 산 상품" 을
 * 노출에서 빼는 데 그 목록을 쓴다.
 */
const personas = source
  .map((p) => ({
    persona_id: p.persona_id,
    skin_type: p.skin_type,
    skin_tone: p.skin_tone,
    eye_color: p.eye_color,
    hair_color: p.hair_color,
    n_reviews: p.n_reviews,
  }))
  .sort((a, b) => a.persona_id.localeCompare(b.persona_id));

const wrong = personas.filter((p) => !p.persona_id.startsWith('PA'));
if (wrong.length > 0) {
  throw new Error(
    `PA 대역이 아닌 페르소나가 ${wrong.length}명 섞였다: ${wrong
      .slice(0, 5)
      .map((p) => p.persona_id)
      .join(', ')}`,
  );
}

const out = join(here, '..', 'src', 'mocks', 'personas.sample.json');
writeFileSync(out, `${JSON.stringify(personas, null, 2)}\n`);

const count = (key: 'skin_type' | 'skin_tone') => {
  const map = new Map<string, number>();
  for (const p of personas) map.set(p[key], (map.get(p[key]) ?? 0) + 1);
  return [...map.entries()].map(([k, v]) => `${k} ${v}`).join(' · ');
};

console.log(`페르소나 ${personas.length}명 → src/mocks/personas.sample.json`);
console.log(`  skin_type  ${count('skin_type')}`);
console.log(`  skin_tone  ${count('skin_tone')}`);
