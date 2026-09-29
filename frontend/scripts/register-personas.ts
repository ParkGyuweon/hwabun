/**
 * 페르소나를 회원으로 일괄 가입시킨다.
 *
 * 데이터 파트의 페르소나 표(PA 대역 100명)를 그대로 shop_backend 회원으로 만든다. 속성 4개
 * (피부 타입·톤·모발색·눈동자색)를 가입 본문에 같이 싣는다 — 프론트 가입 폼이 보내는 것과 같은 필드다
 * (`src/lib/memberProfile.ts` profileToApi). 백엔드 `RegisterMember` 가 아직 그 필드를 안 받으면 무시될 뿐
 * 가입은 된다.
 *
 *   node scripts/register-personas.ts [페르소나 JSON] [--base http://localhost:8090] [--password hwabun1234] [--dry]
 *
 *   기본 파일   ../simulator/personas/data/personas_100_agent.json
 *   이메일      {persona_id 소문자}@persona.hwabun.local   (예: pa00001@persona.hwabun.local)
 *   닉네임      persona_id 그대로 (로그의 persona_id 와 눈으로 맞출 수 있게)
 *   비밀번호    --password 값. 시연 계정과 같은 hwabun1234 가 기본
 *
 * 이미 있는 계정(409)은 건너뛴다. 다시 돌려도 안전하다.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

interface Persona {
  persona_id: string;
  skin_type?: string | null;
  skin_tone?: string | null;
  hair_color?: string | null;
  eye_color?: string | null;
}

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const flag = (name: string, fallback: string): string => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};
const positional = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && args[i - 1].startsWith('--') && args[i - 1] !== '--dry'));

const file = positional[0] ?? join(here, '..', '..', 'simulator', 'personas', 'data', 'personas_100_agent.json');
const base = flag('--base', 'http://localhost:8090').replace(/\/$/, '');
const password = flag('--password', 'hwabun1234');
const dry = args.includes('--dry');

const personas = JSON.parse(readFileSync(file, 'utf8')) as Persona[];
if (!Array.isArray(personas) || personas.length === 0) {
  console.error(`페르소나가 없습니다: ${file}`);
  process.exit(1);
}

const emailOf = (id: string) => `${id.toLowerCase()}@persona.hwabun.local`;
const orNull = (v: unknown) => (typeof v === 'string' && v.trim() ? v : null);

let created = 0;
let existed = 0;
let failed = 0;

for (const p of personas) {
  const body = {
    email: emailOf(p.persona_id),
    password,
    nickname: p.persona_id,
    skinTypeCode: orNull(p.skin_type),
    skinToneCode: orNull(p.skin_tone),
    hairColorCode: orNull(p.hair_color),
    eyeColorCode: orNull(p.eye_color),
    // 시뮬레이션 페르소나 — 필수 동의가 없으면 400, 피부 정보 동의가 없으면 속성 4개가 저장되지 않는다
    agreeTerms: true,
    agreePrivacy: true,
    agreeSkinInfo: true,
    agreeBehaviorLink: true,
  };
  if (dry) {
    console.log(JSON.stringify(body));
    continue;
  }
  try {
    const res = await fetch(`${base}/api/auth/members`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    });
    if (res.status === 201 || res.status === 200) {
      created += 1;
    } else if (res.status === 409) {
      existed += 1;
    } else {
      failed += 1;
      console.error(`${p.persona_id} → ${res.status} ${(await res.text()).slice(0, 200)}`);
    }
  } catch (err) {
    failed += 1;
    console.error(`${p.persona_id} → ${(err as Error).message}`);
  }
}

if (!dry) {
  console.log(`가입 ${created} · 이미 있음 ${existed} · 실패 ${failed} · 전체 ${personas.length}`);
  console.log(`로그인: {persona_id 소문자}@persona.hwabun.local / ${password}`);
  if (failed > 0) process.exit(2);
}
