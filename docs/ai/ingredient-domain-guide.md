# 성분 도메인 가이드 — 어떤 성분이 어떤 피부·고민을 위한 것이고, 행동과 어떻게 잇나

작성: 프론트 (2026-09-07) · 받는 사람: 백엔드 · AI
짝 문서: 백엔드 `ingredient-parsing.md` (성분 파싱·`ingredient`/`product_ingredient` 테이블) ·
[`product-feature-spec.md`](../../contracts/product-feature-spec.md) §2-2 (성분 30종 어휘) ·
[`recommendation-io-spec.md`](../../contracts/recommendation-io-spec.md) §3 (속성 친화도)

근거 표기: `[공개]` 식약처 고시·공식 자료 · `[관행]` 피부과·화장품학에서 널리 통용 · `[추정]` 우리가 정한 값

---

## 0. 먼저 — 무엇을 만들고 무엇을 만들지 않나

백엔드 파싱 문서의 원칙이 맞다. **원문에 없는 함량·효능·안전성은 생성하지 않는다.**
그래서 이 문서가 더하는 것은 상품 데이터가 아니라 **성분 지식 테이블** 이다. 성분 30종에
대해 "무엇을 하는 성분인가, 어느 고민·피부 타입과 맞나, 어느 성분과 같은 계열인가" 를
우리가 정한 값으로 적어 두고, 행동 로그와 사용자 프로필이 이 표를 거쳐 성분 신호가 된다.

```
 product_ingredient (백엔드 파싱)   ×   ingredient_knowledge (이 문서)   ×   행동·프로필
 "이 상품에 이 성분이 n번째"          "이 성분은 모공·지성용, BHA 계열"      "성분 섹션을 오래 봤다, 지성이다"
                                                    ↓
                        "이 사람은 BHA 계열에 반응한다" → 추천 근거 문구 · 배너 축 · 대시보드 성분 인사이트
```

**성분 30종만 다룬다.** 백엔드가 파싱한 2,498종 전부에 지식을 붙이는 것은 불가능하고
필요도 없다. 추천 벡터의 `ingredient` 블록이 30종이고(어휘 기준: 상위 200개 중 5~120개
상품 보유), 소비자가 "성분으로 고른다" 고 할 때 보는 성분도 이 범위다. 나머지 2,468종은
전성분 표시용이다.

---

## 1. 성분 30종 — 기능 계열 · 고민 · 피부 타입

기능 계열은 화장품학에서 통용되는 분류를 우리 어휘에 맞게 7개로 접었다 `[관행]`.
고민 9종은 `concern` 어휘 그대로다. 피부 타입은 `skin_type` 4종(`dry` `oily`
`combination` `normal`) 기준이고, 민감·붉음은 타입이 아니라 고민(`Redness`)으로 본다.

| 어휘 값 (`ingredient`) | 기능 계열 | 주 고민 (`concern`) | 잘 맞는 타입 | 주의 타입·조건 | 대표 INCI (어휘 synonyms) |
|---|---|---|---|---|---|
| Hyaluronic Acid | 보습·수분 | Dryness | 전부 | — | sodium hyaluronate, hyaluronic acid |
| Squalane | 보습·장벽 | Dryness | dry, normal | oily 는 무거울 수 있음 | squalane, squalene |
| Ceramide | 보습·장벽 | Dryness, Redness | dry, 민감 | — | ceramide NP/AP/EOP |
| Shea Butter | 보습·장벽(폐쇄) | Dryness | dry | oily·여드름성은 막힘 주의 | butyrospermum parkii |
| Jojoba | 보습·유분 | Dryness | dry, normal | — | simmondsia chinensis |
| Panthenol (B5) | 보습·진정 | Dryness, Redness | 전부 | — | panthenol |
| Urea | 보습·각질(저농도 보습, 10%+ 각질) | Dryness, Dullness | dry | 고농도는 자극 | urea |
| Mineral Oil / Petrolatum | 장벽(폐쇄) | Dryness | dry, 극건성 | oily 는 기피 성향 큼 | petrolatum, mineral oil |
| Glycerin (어휘 밖, 참고) | 보습 | — | 전부 | — | glycerin |
| Salicylic Acid (BHA) | 각질·모공(지용성) | Pores, Acne/Blemishes | oily, combination | dry·민감은 저농도 | salicylic acid, betaine salicylate |
| AHA/Glycolic Acid | 각질·결(수용성) | Dullness, Dark spots | normal, combination | 민감·붉음 주의, 자차 필수 | glycolic acid |
| Lactic Acid | 각질·결(순한 AHA) | Dullness, Dryness | dry, 민감 | — | lactic acid |
| Willow Bark | 각질·모공(천연 살리실산 유래) | Pores, Acne | oily | — | salix alba bark extract |
| Zinc | 피지·진정 | Pores, Acne, Redness | oily | — | zinc PCA, zinc oxide |
| Niacinamide | 톤·피지·장벽 (다기능) | Dullness, Dark spots, Pores, Redness | 전부 | 고농도(10%+)는 일부 붉음 | niacinamide |
| Vitamin C | 톤·항산화 | Dullness, Dark spots, Anti-Aging | normal, combination | 순수형(ascorbic acid)은 민감 주의 | ascorbic acid, ascorbyl glucoside, 3-o-ethyl ascorbic acid |
| Licorice | 톤·진정 | Dark spots, Redness | 전부 | — | glycyrrhiza glabra |
| Retinol | 항노화·결·모공 | Anti-Aging, Loss of firmness, Pores | normal, oily, combination | 민감·임신 주의, 밤 사용, 자차 필수 | retinol, retinyl palmitate |
| Peptides | 항노화·탄력 | Anti-Aging, Loss of firmness | 전부 | — | palmitoyl tripeptide-1, acetyl hexapeptide-8, copper tripeptide-1 |
| Adenosine | 항노화(주름) | Anti-Aging | 전부 | — | adenosine |
| Collagen | 보습·탄력(표면) | Dryness, Loss of firmness | dry, normal | — | collagen, hydrolyzed collagen |
| Caffeine | 부기·다크서클 | Dark Circles | 전부 | — | caffeine |
| Centella (Cica) | 진정·장벽 회복 | Redness, Acne | 민감, 전부 | — | centella asiatica, madecassoside, asiaticoside |
| Allantoin | 진정 | Redness | 민감, 전부 | — | allantoin |
| Aloe | 진정·수분 | Redness, Dryness | 전부 | — | aloe barbadensis |
| Green Tea | 항산화·진정·피지 | Redness, Pores, Anti-Aging | oily, combination | — | camellia sinensis |
| Probiotic / Ferment | 장벽·컨디셔닝 | Dullness, Redness | 전부 | — | lactobacillus ferment, galactomyces |
| Rosehip / Rose | 보습·톤·향 | Dryness, Dullness | dry, normal | 향 민감 주의 | rosa canina, rosa damascena |
| SPF | 자외선 차단 | Dark spots, Anti-Aging (예방) | 전부 | 산화아연·티타늄은 백탁 | titanium dioxide, zinc oxide, ethylhexyl triazone |
| Silicone | 사용감·마감 | (텍스처) | 전부 | 일부 사용자 기피(`Without Silicones`) | dimethicone, cyclopentasiloxane |
| Alcohol Denat | 사용감·침투(휘발) | (텍스처) | oily 는 선호하기도 | dry·민감 기피 | alcohol denat |

**표를 읽는 규칙 세 가지.**

1. "잘 맞는 타입" 은 그 성분이 **주로 겨냥하는** 피부이지, 다른 타입이 쓰면 안 된다는 뜻이
   아니다. 히알루론산은 전 타입, 시어버터는 건성 중심 같은 정도의 경향이다 `[관행]`.
2. "주의" 는 자극·막힘 가능성이다. 위해 판정이 아니다. 대시보드의 "주의 성분" 이 "확인 필요"
   톤을 쓰는 것과 같은 이유다 (`metrics.ts` CAUTION_INGREDIENTS 주석).
3. 한 성분이 여러 고민에 걸친다. 나이아신아마이드가 대표적이다. 매핑 테이블은 **다대다** 로,
   각 쌍에 강도(1 주 · 0.5 보조)를 둔다.

### 1-1. 식약처 기능성 화장품 고시 원료 `[공개]` — 함량이 "말이 되는" 기준

한국 데이터를 받을 때 등록 폼의 함량(%)이 이 범위 안이면 기능성 표방이 가능한 함량이라는
뜻이다. 추천에는 쓰지 않고 **등록 검증과 표시 문구** 에 쓴다.

| 기능 | 원료 | 고시 함량 |
|---|---|---|
| 미백 | 나이아신아마이드 (Niacinamide) | 2~5% |
| 미백 | 알부틴 (Arbutin) | 2~5% |
| 미백 | 에칠아스코빌에텔 (3-O-Ethyl Ascorbic Acid) | 1~2% |
| 미백 | 아스코빌글루코사이드 (Ascorbyl Glucoside) | 2% |
| 주름 개선 | 아데노신 (Adenosine) | 0.04% |
| 주름 개선 | 레티놀 (Retinol) | 2,500 IU/g |
| 주름 개선 | 레티닐팔미테이트 | 10,000 IU/g |

출처: 식약처 「기능성화장품 심사에 관한 규정」 별표 4 (고시 원료). 함량이 이 범위를 벗어나면
기능성 표방을 못 하는 것이지, 성분이 없는 것이 아니다. 등록 폼에서는 **범위 밖이면 경고만**
띄운다.

### 1-2. 제품의 목적 — 카테고리 19종은 "무엇을 위한 제품인가"

성분만으로는 목적을 모른다. 같은 살리실산이 클렌저에 있으면 씻어 내는 각질 관리이고
세럼에 있으면 남겨 두는 모공 관리다. 그래서 `tertiary_category` 19종을 **루틴 단계 · 기대
효과 · 그 목적에 흔히 쓰는 성분 계열** 로 잇는다 `[관행]`. 추천 근거("세안 단계의 …")와
등록 폼의 카테고리 안내, 배너 `category` 축 문구에 쓴다.

| `tertiary_category` (어휘 원문) | 루틴 단계 | 목적 (기대 효과) | 흔한 핵심 성분 계열 | 남기나 |
|---|---|---|---|---|
| Face Wash & Cleansers | 1 세안 | 피지·노폐물 제거, 당김 없이 | 아미노산계 세정, Salicylic Acid(지성용), Green Tea | 씻어 냄 |
| Makeup Removers | 1 세안 | 메이크업·자차 용해 | 오일·에스터, Jojoba | 씻어 냄 |
| Face Wipes | 1 세안(간이) | 간편 세정 | 보습·진정(Aloe) | 씻어 냄 |
| Exfoliators | 2 각질 | 결·모공 정돈 (물리·화학) | AHA/Glycolic Acid, Lactic Acid, Salicylic Acid, Willow Bark | 대부분 씻어 냄 |
| Facial Peels | 2 각질(집중) | 주 1~2회 강한 각질 | AHA/Glycolic Acid 고농도, Salicylic Acid | 씻어 냄 |
| Toners | 3 토닝 | pH·수분 정돈, 다음 단계 흡수 | Hyaluronic Acid, Niacinamide, Centella, Panthenol | 남김 |
| Mists & Essences | 3 토닝/보습 | 가벼운 수분·컨디셔닝 | Probiotic / Ferment, Hyaluronic Acid | 남김 |
| Face Serums | 4 집중 | 고민 하나를 겨냥 (톤·모공·주름·진정) | Vitamin C, Niacinamide, Retinol, Peptides, Adenosine, Centella | 남김 |
| Blemish & Acne Treatments | 4 집중(국소) | 트러블 부위 | Salicylic Acid, Zinc, Centella | 남김 |
| Face Oils | 5 보습(유분) | 장벽·유수분 균형 | Squalane, Jojoba, Rosehip / Rose | 남김 |
| Moisturizers | 5 보습 | 수분 유지·장벽 | Hyaluronic Acid, Ceramide, Squalane, Shea Butter, Glycerin | 남김 |
| Night Creams | 5 보습(밤) | 밤 회복·항노화 | Retinol, Peptides, Ceramide, Shea Butter | 남김 |
| For Face (기타) | 5 보습/집중 | 분류 밖 페이스 케어 | — | 남김 |
| Eye Creams & Treatments | 6 아이 | 다크서클·잔주름·부기 | Caffeine, Peptides, Retinol(저농도), Hyaluronic Acid | 남김 |
| Eye Masks | 6 아이(집중) | 부기·수분 집중 | Caffeine, Hyaluronic Acid, Collagen | 씻어 냄/떼어 냄 |
| Face Masks | 7 마스크 | 주 1~3회 집중 수분·진정·각질 | Hyaluronic Acid, Centella, Collagen, (클레이) | 씻어 냄/떼어 냄 |
| Face Sunscreen | 8 차단 | 자외선 차단, 색소·노화 예방 | SPF(유·무기 차단제), Niacinamide, Hyaluronic Acid | 남김 |
| BB & CC Creams | 8 차단+톤 | 차단 + 가벼운 커버 | SPF, Silicone, Niacinamide | 남김 |
| Lip Balms & Treatments | 립 | 입술 보습·보호 | Shea Butter, Mineral Oil / Petrolatum, Squalane | 남김 |

**읽는 규칙.**

1. "씻어 냄" 제품의 성분은 남는 시간이 짧아 **성분 관심 신호의 무게를 낮춘다** (§3 에서
   `ing_weight × 0.5`). 클렌저에 든 살리실산을 오래 봤다고 BHA 선호로 세게 잡으면 안 된다.
2. 같은 목적 안에서만 `similar` 대체를 제안한다. 세럼의 대체는 세럼이지 토너가 아니다.
3. 루틴 단계 번호는 **`synergy` 조합의 순서** 이기도 하다 (세안 → 각질 → 토닝 → 집중 → 보습
   → 차단). "다음 단계 제안" 은 이 번호로 만든다.
4. 등록 폼에서 브랜드가 카테고리를 고르면 이 표의 "목적" 을 안내 문구로 보여 주고, 고른
   카테고리와 어울리지 않는 `highlights` 조합(예: Face Sunscreen 인데 concern 태그가 하나도
   없음)이면 경고만 띄운다.

---

## 2. 성분 간 관계 — 유사 · 대체 · 시너지 · 동시 사용 주의

추천에서 "비슷한 성분 구성" 을 말하려면 성분끼리의 관계가 필요하다. 30종 안에서 관계를
정의한다. 관계 종류는 네 가지다.

| 관계 | 뜻 | 추천에서의 쓰임 |
|---|---|---|
| `similar` | 같은 기능 계열, 서로 바꿔 써도 목적이 같다 | "이 상품과 성분 구성이 유사" 문구, 대체 상품 |
| `alternative` | 다른 계열이지만 같은 고민을 다른 방식으로 푼다 | 자극이 걱정되는 사용자에게 순한 쪽 제안 |
| `synergy` | 같이 쓰면 흔히 권장 | 세트·다음 단계 제안 |
| `caution_together` | 같이 쓰면 자극·불안정이 흔히 지적됨 | 장바구니에 둘 다 있으면 안내, 추천 조합에서 회피 |

| A | B | 관계 | 메모 `[관행]` |
|---|---|---|---|
| Salicylic Acid | Willow Bark | similar | 버드나무 껍질은 살리실산 유래. 순한 쪽 |
| Salicylic Acid | AHA/Glycolic Acid | alternative | BHA 는 지용성(모공 속), AHA 는 수용성(표면 결) |
| AHA/Glycolic Acid | Lactic Acid | similar | 둘 다 AHA. 락틱이 분자가 커서 순함 |
| Hyaluronic Acid | Collagen | similar | 표면 보습·탄력감. 둘 다 흡수보다 보습막 |
| Ceramide | Squalane | similar | 장벽 지질 계열 |
| Shea Butter | Mineral Oil / Petrolatum | similar | 폐쇄막 보습 |
| Ceramide | Niacinamide | synergy | 장벽 회복 조합으로 흔히 권장 |
| Hyaluronic Acid | Ceramide | synergy | 수분 + 장벽 |
| Retinol | Peptides | alternative | 레티놀 자극이 걱정되면 펩타이드 |
| Retinol | Adenosine | alternative | 고시 주름 원료 두 가지 |
| Retinol | Niacinamide | synergy | 레티놀 자극 완화 조합으로 흔히 권장 |
| Vitamin C | SPF | synergy | 낮 항산화 + 차단 |
| Vitamin C | Licorice | similar | 톤·다크스팟 |
| Centella (Cica) | Allantoin | similar | 진정 |
| Centella (Cica) | Panthenol (B5) | similar | 진정·장벽 |
| Aloe | Allantoin | similar | 진정·수분 |
| Zinc | Niacinamide | synergy | 피지·모공 조합 (예: 나이아신아마이드 10% + 징크 1%) |
| Green Tea | Zinc | similar | 피지·항산화 |
| Retinol | AHA/Glycolic Acid | caution_together | 같은 루틴에서 자극 누적. 밤/아침 분리 권장 |
| Retinol | Salicylic Acid | caution_together | 위와 같음 |
| Retinol | Vitamin C (순수형) | caution_together | pH·자극. 아침 C / 밤 레티놀로 분리 |
| Vitamin C (순수형) | AHA/Glycolic Acid | caution_together | 저pH 중첩 자극 |
| Alcohol Denat | Retinol | caution_together | 건조·자극 누적 |

**옛날 통념 하나는 넣지 않는다.** "나이아신아마이드 + 비타민C 는 같이 쓰면 안 된다" 는
1960년대 고온 조건 실험에서 온 이야기이고 현재 처방에서는 흔히 같이 쓴다 `[관행]`.
`caution_together` 에 넣지 않는다.

---

## 3. 행동 → 성분 신호 — 이미 있는 이벤트로 잡는다

새 이벤트는 없다. 성분에 닿는 행동은 이미 다섯 가지가 로그에 있다.

| 이벤트 | 성분 정보 | 신호 세기 `[추정]` | 비고 |
|---|---|---|---|
| `text_selection` / `text_copy` | `matched_ingredients[]` (어휘 30종 표준명) | 선택 1.5 · 복사 2.0 | 어느 성분을 **직접 짚었나**. 가장 정확한 신호 |
| `section_dwell` (`section_id=ingredients`) | 상품의 성분 30종 전부 (position 가중) | 초당 1.0, 상한 60초 | 성분표를 읽었다. 무엇을 봤는지는 상품 성분으로 대신 |
| `ingredient_view_mode_change` | 위와 같음 | 1.5 | 표시 방식을 바꿀 만큼 관심 |
| `accordion_toggle` (`ingredients`, expand) | 위와 같음 | 1.0 | |
| `purchase_reason_select` (`ingredient` · `clean_claim`) | 산 상품의 성분 30종 | 2.0 | **선언** 신호. 행동 추론과 대조 |
| `filter_change` (`ingredient_exclude`) | 기피 성분 | −2.0 (기피 벡터) | 화면 없음. 계약 §3.8 미등록 |

계산은 사용자 벡터와 같은 꼴이다. 성분 30차원 벡터 두 개를 둔다.

```
u_ing⁺[i] = Σ_events  w_event × decay(t) × ing_weight(product, i)     관심 성분
u_ing⁻[i] = Σ_events  w_event × decay(t) × ing_weight(product, i)     기피 성분 (제외 필터 · 담았다 뺀 상품)

ing_weight(product, i) = 어휘집 위치가중  max(1 − 등장위치/전체성분수, 0.1)
                          (product-feature-vocab.json ingredient_source.position_formula 와 같은 식)
                          × 0.5  if 씻어 내는 제품 (§1-2 "남기나" 열)
text_selection 은 matched_ingredients 에 든 성분만 1.0
```

이건 AI 파트의 사용자 벡터 148차원 중 `ingredient` 블록 30차원을 **따로 읽는 것** 과
거의 같다. 새로 만들 필요 없이 `user:vec:{id}` 의 해당 슬라이스를 쓰면 되는지 AI 파트
확인이 필요하다 (§6 질문 1).

---

## 4. 프로필 → 성분 사전 확률 — 행동이 없을 때

가입 시 받는 `skin_type`(4) · `skin_tone`(5) 과 사용자가 고른 피부 고민(0~N, 백엔드 신설
요청)으로 성분 사전 확률을 만든다. §1 표의 "잘 맞는 타입" 과 "주 고민" 열을 뒤집은 것이다.

```
prior_ing[i] = 0.5                                      기본 중립 (attr_affinity 의 중립값과 같다)
             + 0.3 × [i 의 잘 맞는 타입에 skin_type 포함]
             − 0.3 × [i 의 주의 타입에 skin_type 포함]
             + 0.2 × Σ_{c ∈ 사용자 고민} strength(i, c)   (주 1.0 · 보조 0.5)
clip 0~1
```

`[추정]` 값이다. 리뷰 기반 `attr_affinity`(상품 × 세그먼트 lift) 가 실측이라면 이것은
**지식 기반** 이라 서로 보완한다. 행동이 쌓이면(§3 벡터의 가중치 합 ≥ 2.0) 사전 확률은
0.5 무게로 내리고 행동을 앞세운다 — `recommendation-io-spec` §5 의 가중치 스케줄과 같은
사고방식이다.

**복합성(55%)은 여기서도 애매하다.** 타입으로는 T존 지성·볼 건성이라 "잘 맞는 타입" 이
갈린다. 복합성은 타입 항을 0 으로 두고 **고민 항만** 쓴다. `attr_affinity` 가 복합성에
`skin_type` 가중을 0 으로 두는 것과 같은 판단이다.

---

## 5. 백엔드 테이블 제안 — 파싱 테이블 위에 지식 테이블

백엔드 문서의 `ingredient` · `product_ingredient` · `ingredient_alias` 는 그대로 둔다.
그 위에 **30종만 있는** 지식 테이블 넷을 얹는다. 파싱 결과(2,498종)와 지식(30종)을 잇는
열쇠는 어휘집의 `synonyms` 다 — `ingredient_code` 를 소문자 부분 일치로 30종 표준명에
매핑하는 배치 한 번이면 된다.

```
ingredient_vocab                 어휘 30종. product-feature-vocab.json 이 원본
- vocab_key         PK  "Salicylic Acid"  (어휘집 문자열 그대로, 한 글자도 바꾸지 않는다)
- label_ko              "살리실산"       (product-form-labels-ko.json)
- function_group        보습장벽 | 각질모공 | 톤 | 항노화 | 진정 | 자차 | 사용감
- vocab_version         "0.5"

ingredient_vocab_map             파싱 성분 → 어휘 30종 (다대일)
- ingredient_code   FK ingredient
- vocab_key         FK ingredient_vocab
- match_rule            synonym 문자열
- mapping_status        auto | reviewed

ingredient_concern               §1 "주 고민" 열
- vocab_key · concern_value ("Pores" …, concern 어휘 원문) · strength (1.0 | 0.5)

ingredient_skin_fit              §1 "잘 맞는 / 주의" 열
- vocab_key · skin_type (dry|oily|combination|normal) · fit (+1 | 0 | −1)

ingredient_relation              §2
- vocab_key_a · vocab_key_b · relation (similar|alternative|synergy|caution_together) · note
```

`concern_value` · `skin_type` · `vocab_key` 가 전부 **어휘집 원문** 인 이유는 배너·추천·
등록 폼이 같은 문자열을 쓰기 때문이다. 한 글자 다르면 매칭이 조용히 실패한다.

**함량(`concentration_value`)** 은 백엔드 문서 제안대로 한국 데이터에서만 받고, 있을 때
§1-1 고시 범위와 대조해 `functional_claim_ok` 플래그를 파생한다. 추천 점수에는 넣지 않는다.

---

## 6. 어디에 쓰이나 — 세 화면

| 화면 | 쓰는 것 | 문구 예 |
|---|---|---|
| 추천 근거 (`reason.content`) | `ingredient_relation.similar` + 사용자 관심 성분 | "회원님이 자주 본 BHA 계열(살리실산·버드나무)이 앞쪽에 있는 제품" |
| 배너 `ingredient` 축 | 사용자 관심 성분 상위 1개 → 그 성분이 앞쪽인 상품 | "살리실산이 들어간" |
| 브랜드 대시보드 성분 인사이트 | `ingredient_concern` 로 "등록 태그 vs 고객 반응 성분" 대조 | "태그는 진정인데 고객은 성분표에서 나이아신아마이드를 긁어 간다" |
| 장바구니 | `caution_together` | "레티놀과 AHA 가 같이 담겼습니다. 아침·밤으로 나눠 쓰는 것을 권합니다" |

---

## 7. 확인이 필요한 것

**AI 파트**
1. §3 의 성분 30차원 벡터가 `user:vec:{id}` 의 `ingredient` 블록 슬라이스와 같은 것인지.
   같다면 별도 계산 없이 그 슬라이스를 노출해 주시면 된다.
2. §4 사전 확률을 `attr_affinity` 의 중립 0.5 와 같은 자리에서 섞어도 되는지, 아니면
   콜드스타트 전용으로만 둘지.
3. `ingredient_relation.similar` 를 콘텐츠 벡터 유사도 대신 설명 문구에만 쓰는 게 맞는지.

**백엔드 파트**
4. §5 테이블 넷을 파싱 테이블 옆에 두는 구조가 괜찮은지. `ingredient_vocab_map` 배치는
   어휘집 synonyms 로 프론트가 만들어 드릴 수 있다.
5. 사용자 피부 고민(다중) 테이블 신설 — 코드표는 `concern` 어휘 9종 공유.
6. 한국 데이터 함량 파싱(`%`, `ppm`) 은 백엔드 문서 §"한국 소규모 화장품" 순서대로 가되,
   §1-1 고시 범위 대조는 등록 검증 단계에 두면 되는지.
