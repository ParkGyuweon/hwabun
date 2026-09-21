-- SSAFY Beauty 상품 3개에 두 번째 옵션을 더한다 (2026-09-21).
-- 대시보드 "옵션을 오간 횟수" 는 옵션이 둘 이상일 때만 기록이 생긴다. 시연 브랜드 8개가 전부 "기본" 하나여서 늘 0 이었다.
-- 기존 *-V1 은 장바구니·주문이 참조하므로 건드리지 않고 sort_order 1 로 추가만 한다. 같은 값이 frontend/src/mocks/products.ssafy-beauty.json 에도 있다.
INSERT INTO product_variant (variant_id,product_id,sku_id,label,label_ko,size,size_ko,price_krw,sale_price_krw,image_url,swatch_url,status,sort_order) VALUES
('SB000001-V2','SB000001','SB000001-140','대용량','대용량','140매 / 310g',NULL,'52000','44200','/images/ssafy-beauty/SB000001-m2.webp',NULL,'ACTIVE','1'),
('SB000004-V2','SB000004','SB000004-220','대용량','대용량','220ml',NULL,'61000','52000','/images/ssafy-beauty/SB000004-m2.webp',NULL,'ACTIVE','1'),
('SB000007-V2','SB000007','SB000007-REFILL','리필','리필','20ml',NULL,'24000','20400','/images/ssafy-beauty/SB000007-m2.webp',NULL,'ACTIVE','1')
ON DUPLICATE KEY UPDATE label=VALUES(label),label_ko=VALUES(label_ko),size=VALUES(size),price_krw=VALUES(price_krw),sale_price_krw=VALUES(sale_price_krw),image_url=VALUES(image_url),status=VALUES(status);
