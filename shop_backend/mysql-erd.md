# Shop Backend MySQL ERD

현재 MVP DDL은 29개 테이블입니다. 계정·상품·상품 속성·주문·리뷰·피드백·정산을 MySQL에 저장하고 추천 벡터와 DW 집계 결과는 별도 영역에서 관리합니다.

## 관계

SELLER_ACCOUNT 1:N BRAND 1:N PRODUCT 1:N PRODUCT_VARIANT
MEMBER 1:1 CART 1:N CART_ITEM
MEMBER 1:N SHOP_ORDER 1:N ORDER_ITEM
ORDER_ITEM 1:0..1 REVIEW, ORDER_ITEM 1:0..1 FEEDBACK
BRAND 1:N SETTLEMENT 1:N SETTLEMENT_ITEM
PRODUCT N:M SKIN_TYPE, CONCERN, CLEAN, TEXTURE, INGREDIENT

## 테이블 구성

| 영역 | 테이블 | 설명 |
|---|---|---|
| 계정 | seller_account, member, admin_account | 사업자·회원·관리자 계정. member는 피부 타입·피부색·헤어 색·눈동자 색 FK를 가진다. |
| 브랜드 | brand | seller_account가 소유하는 브랜드. |
| 기준값 | skin_type, skin_tone, hair_color, eye_color, concern, category | 회원과 상품이 공유하는 코드 및 카테고리 계층. |
| 상품 | product | 브랜드, 카테고리, price_bin, secondary/tertiary category와 원문 정보를 저장한다. |
| 상품 미디어 | product_image | 상품 이미지와 표시 순서. |
| 상품 옵션 | product_variant | SKU·용량·원화 가격. |
| 상품 속성 | product_skin_type, product_concern, product_clean, product_texture | 상품의 피부 타입·고민·clean·texture 다대다 연결. |
| clean/texture 기준 | clean_feature, texture_feature | 계약에 정의된 clean 16종·texture 5종 코드. |
| 성분 | ingredient, product_ingredient | 상품 성분, 순서(first_position), 파서 버전. |
| 구매 | cart, cart_item, shop_order, order_item | 장바구니·주문. member_id + idempotency_key UNIQUE로 중복 주문을 방지한다. |
| 의견 | review, feedback | 구매 후기와 구매 후 개선 의견. |
| 정산 | settlement, settlement_item | 브랜드 월별 정산과 정산 대상 주문 상품. |

## 제거한 테이블

추천 벡터·속성 친화도·페르소나·DW용 수입 리뷰 테이블은 제거했습니다. 상품 원천 속성은 모두 보존해야 하므로 clean/texture 코드와 매핑 테이블은 다시 포함했습니다.

실행 DDL: mysql-erd.sql
