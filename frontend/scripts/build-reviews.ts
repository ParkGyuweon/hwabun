/**
 * 리뷰 목 데이터를 만든다.
 *
 * 입력  simulator/personas/data/personas_*.json  실제 세포라 리뷰어 10,000명의 리뷰 이력
 * 출력  src/mocks/reviews.sample.json
 *
 * 리뷰를 따로 수집할 필요가 없다. **페르소나가 실제 리뷰어 본인**이라
 * 그 사람이 쓴 리뷰가 페르소나 데이터에 그대로 들어 있다.
 * 별점·본문·작성일·피부 속성까지 원본이다.
 *
 * 상품 200개 목록은 사이즈 변형을 병합한 그룹이라, 리뷰의 `group_id` 로 조인한다.
 * 대표 `product_id` 로만 조인하면 형제 상품(미니·리필)의 리뷰가 누락된다.
 *
 *   npx tsx scripts/build-reviews.ts
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');

/**
 * 상품당 담을 리뷰 수.
 *
 * 리뷰 섹션·필터·평점 분포를 굴리는 데 필요한 만큼만 담는다.
 * 목 데이터가 번들에 그대로 들어가므로 무한정 늘릴 수 없다.
 *
 * 15건일 때 파일이 2MB, 번들이 2.4MB 가 됐다. 체류 시간을 재는 페이지에서
 * 로드가 느려지면 그게 측정값에 섞이므로 10건으로 줄였다.
 * 본문 평균이 341자라 건수가 그대로 용량이 된다.
 */
const PER_PRODUCT = 10;

interface PersonaReview {
  review_id: string;
  product_id: string;
  group_id: string;
  rating: number;
  is_recommended: boolean | null;
  review_title: string | null;
  review_text: string | null;
  submission_time: string;
  skin_type: string;
  skin_tone: string;
  eye_color: string;
  hair_color: string;
}

interface Persona {
  author_id: string;
  reviews: PersonaReview[];
}

function loadPersonas(file: string): Persona[] {
  const parsed = JSON.parse(readFileSync(join(root, 'simulator', 'personas', 'data', file), 'utf8'));
  return Array.isArray(parsed) ? parsed : (Object.values(parsed)[0] as Persona[]);
}

const personas = [
  ...loadPersonas('personas_100_agent.json'),
  ...loadPersonas('personas_9900.json'),
];

const products = JSON.parse(
  readFileSync(join(root, 'batch', 'ingest', 'data', 'products_200.json'), 'utf8'),
) as Array<{ product_id: string; _merged?: { member_product_ids?: string[] } }>;

/**
 * 리뷰의 상품 ID → 200개 목록의 대표 ID.
 * 병합된 형제 상품 ID 도 대표로 접어 넣는다.
 */
const toRepresentative = new Map<string, string>();
for (const product of products) {
  toRepresentative.set(product.product_id, product.product_id);
  for (const member of product._merged?.member_product_ids ?? []) {
    toRepresentative.set(member, product.product_id);
  }
}

const buckets = new Map<string, Array<Record<string, unknown>>>();
const seen = new Set<string>();
let skipped = 0;

for (const persona of personas) {
  for (const review of persona.reviews ?? []) {
    const target =
      toRepresentative.get(review.group_id) ?? toRepresentative.get(review.product_id);

    // 200개 목록에 없는 상품(제외된 보충제 등)의 리뷰는 버린다
    if (!target) {
      skipped += 1;
      continue;
    }

    const bucket = buckets.get(target) ?? [];
    if (bucket.length >= PER_PRODUCT) continue;

    // 같은 리뷰가 여러 페르소나에 걸쳐 중복될 수 있다
    if (seen.has(review.review_id)) continue;
    seen.add(review.review_id);

    bucket.push({
      review_id: review.review_id,
      // 화면은 대표 ID 로 조회하므로 대표로 맞춰 담는다
      product_id: target,
      author_id: persona.author_id,
      rating: review.rating,
      is_recommended: review.is_recommended,
      review_title: review.review_title,
      review_text: review.review_text,
      submission_time: review.submission_time,
      skin_type: review.skin_type,
      skin_tone: review.skin_tone,
      eye_color: review.eye_color,
      hair_color: review.hair_color,
    });
    buckets.set(target, bucket);
  }
}

/**
 * 본문이 있는 리뷰를 앞으로 보낸다.
 * 화면이 본문을 보여주는데 앞쪽이 전부 빈 리뷰면 섹션이 비어 보인다.
 */
const reviews = products
  .flatMap((product) => buckets.get(product.product_id) ?? [])
  .sort((a, b) => Number(Boolean(b.review_text)) - Number(Boolean(a.review_text)));

// 2,000건짜리 생성 파일은 사람이 열어보지 않는다. 들여쓰기를 빼서 용량을 줄인다
writeFileSync(
  join(here, '..', 'src', 'mocks', 'reviews.sample.json'),
  `${JSON.stringify(reviews)}\n`,
  'utf8',
);

const covered = [...buckets.keys()].length;
const withText = reviews.filter((r) => r.review_text).length;
const counts = products.map((p) => buckets.get(p.product_id)?.length ?? 0);

console.log(`리뷰 ${reviews.length}건 작성 → src/mocks/reviews.sample.json`);
console.log(`  리뷰가 붙은 상품   ${covered} / ${products.length}`);
console.log(`  본문 있는 리뷰     ${withText} (${Math.round((withText / reviews.length) * 100)}%)`);
console.log(`  상품당 최소 / 최대 ${Math.min(...counts)} / ${Math.max(...counts)}`);
console.log(`  목록에 없는 상품 리뷰 버림 ${skipped.toLocaleString()}건`);
