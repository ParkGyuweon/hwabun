# 테이블 설명

최종 기준은 [mysql-erd.md](mysql-erd.md)와 [mysql-erd.sql](mysql-erd.sql)입니다. 총 29개 테이블이며, 쇼핑몰 서버의 영속 데이터만 둡니다.

## 계정·브랜드

- seller_account: 사업자 로그인 계정
- member: 구매자 계정과 피부 타입·피부 톤·헤어 색·눈동자 색 FK
- admin_account: 운영자 로그인 계정
- brand: seller_account가 소유하는 브랜드

## 기준값

- skin_type / skin_tone / hair_color / eye_color: 회원·상품 속성 코드
- concern: 피부 고민 코드
- category: 상품 카테고리 계층

## 상품

- product: 브랜드 상품 본체. 계약의 brand, concern, ingredient, clean, secondary_category, tertiary_category, price_bin, texture, 가격·평점·인기도와 등록 원문을 보관
- product_variant: SKU·용량·원화 가격
- product_image: 상세 이미지
- clean_feature / texture_feature: clean·texture 코드표
- product_skin_type / product_concern / product_clean / product_texture: 상품 속성 연결
- ingredient / product_ingredient: 성분 기준값과 상품별 파싱 결과
- product_unmapped_value: 등록 vocab 밖 입력을 상품·필드·원문 값 단위로 수집

clean과 texture는 코드표와 다대다 매핑으로 저장합니다. 원문 보존이 필요한 경우 product.clean_json, product.texture_json도 함께 사용할 수 있습니다.

## 구매·의견·정산

- cart / cart_item: 회원 장바구니
- shop_order / order_item: 주문과 구매 당시 상품 스냅샷. member_id + idempotency_key 유일 제약으로 중복 주문을 막음
- review: 구매 후기
- feedback: 구매 후 개선 의견. member/product/axis와 결제 완료 order_item 증빙을 보관하며 회원·상품·축별 1건만 허용한다.
- feedback_classification / feedback_classification_label: 분류 워커가 채울 상태·메타데이터와 다중 라벨 저장 공간. 현재 API는 PENDING 상태만 생성하며 AI 호출·금지어 처리는 별도 영역이다.
- settlement / settlement_item: 브랜드별 월 정산

추천 벡터, 페르소나, DW 집계용 리뷰·속성 친화도 테이블은 이 DB에서 제거하고 Redis/AI/DW에서 관리합니다.
