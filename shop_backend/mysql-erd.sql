-- MySQL 8.0+ DDL for the shop backend MVP
CREATE DATABASE IF NOT EXISTS shop_backend CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE shop_backend;

CREATE TABLE seller_account (
 seller_account_id VARCHAR(64) PRIMARY KEY, email VARCHAR(320) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, name VARCHAR(100) NOT NULL,
 status ENUM('ACTIVE','INACTIVE','LOCKED') NOT NULL DEFAULT 'ACTIVE', created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);
CREATE TABLE member (
 member_id VARCHAR(64) PRIMARY KEY, email VARCHAR(320) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, nickname VARCHAR(100) NOT NULL,
 status ENUM('ACTIVE','INACTIVE','LOCKED') NOT NULL DEFAULT 'ACTIVE', skin_type_code VARCHAR(32) NULL, skin_tone_code VARCHAR(32) NULL, hair_color_code VARCHAR(32) NULL, eye_color_code VARCHAR(32) NULL,
 created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);
CREATE TABLE admin_account (
 admin_account_id VARCHAR(64) PRIMARY KEY, email VARCHAR(320) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, name VARCHAR(100) NOT NULL,
 status ENUM('ACTIVE','INACTIVE','LOCKED') NOT NULL DEFAULT 'ACTIVE', created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);
CREATE TABLE brand (
 brand_id VARCHAR(64) PRIMARY KEY, seller_account_id VARCHAR(64) NOT NULL, name VARCHAR(200) NOT NULL, description TEXT NULL, logo_url VARCHAR(1000) NULL,
 status ENUM('ACTIVE','INACTIVE') NOT NULL DEFAULT 'ACTIVE', created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
 FOREIGN KEY(seller_account_id) REFERENCES seller_account(seller_account_id) ON DELETE RESTRICT, UNIQUE KEY uq_brand_seller_name (seller_account_id,name)
);
CREATE TABLE skin_type (code VARCHAR(32) PRIMARY KEY, label_ko VARCHAR(50) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE);
CREATE TABLE skin_tone (code VARCHAR(32) PRIMARY KEY, label_ko VARCHAR(50) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE);
CREATE TABLE hair_color (code VARCHAR(32) PRIMARY KEY, label_ko VARCHAR(50) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE);
CREATE TABLE eye_color (code VARCHAR(32) PRIMARY KEY, label_ko VARCHAR(50) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE);
CREATE TABLE concern (code VARCHAR(64) PRIMARY KEY, label_ko VARCHAR(100) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE);
ALTER TABLE member ADD CONSTRAINT fk_member_skin_type FOREIGN KEY(skin_type_code) REFERENCES skin_type(code);
ALTER TABLE member ADD CONSTRAINT fk_member_skin_tone FOREIGN KEY(skin_tone_code) REFERENCES skin_tone(code);
ALTER TABLE member ADD CONSTRAINT fk_member_hair_color FOREIGN KEY(hair_color_code) REFERENCES hair_color(code);
ALTER TABLE member ADD CONSTRAINT fk_member_eye_color FOREIGN KEY(eye_color_code) REFERENCES eye_color(code);

CREATE TABLE category (
 category_id VARCHAR(64) PRIMARY KEY, parent_id VARCHAR(64) NULL, code VARCHAR(100) NOT NULL UNIQUE, name VARCHAR(200) NOT NULL, depth TINYINT NOT NULL, sort_order INT NOT NULL DEFAULT 0, is_active BOOLEAN NOT NULL DEFAULT TRUE,
 FOREIGN KEY(parent_id) REFERENCES category(category_id) ON DELETE RESTRICT
);
CREATE TABLE product (
 product_id VARCHAR(64) PRIMARY KEY, brand_id VARCHAR(64) NOT NULL, category_id VARCHAR(64) NOT NULL, product_name VARCHAR(300) NOT NULL,
 product_source ENUM('seed_catalog','brand_registered') NOT NULL, status ENUM('DRAFT','PENDING_APPROVAL','ACTIVE','INACTIVE','REJECTED') NOT NULL DEFAULT 'DRAFT',
 secondary_category VARCHAR(64) NOT NULL, tertiary_category VARCHAR(64) NOT NULL, price_bin VARCHAR(16) NOT NULL, rating DECIMAL(4,2) NULL, loves_count INT NULL,
 primary_image_url VARCHAR(1000) NULL, description_json JSON NULL, ingredients_text TEXT NULL, clean_json JSON NULL, texture_json JSON NULL,
 source_price_usd DECIMAL(12,2) NULL, source_rating DECIMAL(4,2) NULL, source_review_count INT NULL, source_loves_count INT NULL, source_rank INT NULL,
 created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
 FOREIGN KEY(brand_id) REFERENCES brand(brand_id) ON DELETE RESTRICT, FOREIGN KEY(category_id) REFERENCES category(category_id) ON DELETE RESTRICT,
 UNIQUE KEY uq_product_brand(product_id,brand_id), INDEX ix_product_brand_status(brand_id,status), INDEX ix_product_category_status(category_id,status)
);
CREATE TABLE product_variant (
 variant_id VARCHAR(64) PRIMARY KEY, product_id VARCHAR(64) NOT NULL, sku_id VARCHAR(64) NOT NULL UNIQUE, label VARCHAR(200) NOT NULL, size VARCHAR(100) NULL,
 price_krw DECIMAL(18,0) NOT NULL, sale_price_krw DECIMAL(18,0) NULL, image_url VARCHAR(1000) NULL, swatch_url VARCHAR(1000) NULL, status ENUM('ACTIVE','INACTIVE') NOT NULL DEFAULT 'ACTIVE', sort_order INT NOT NULL DEFAULT 0,
 FOREIGN KEY(product_id) REFERENCES product(product_id) ON DELETE RESTRICT, UNIQUE KEY uq_variant_order(product_id,sort_order), CHECK(price_krw > 0), CHECK(sale_price_krw IS NULL OR (sale_price_krw > 0 AND sale_price_krw <= price_krw))
);
CREATE TABLE product_image (
 image_id VARCHAR(64) PRIMARY KEY, product_id VARCHAR(64) NOT NULL, url VARCHAR(1000) NOT NULL, sort_order INT NOT NULL,
 FOREIGN KEY(product_id) REFERENCES product(product_id) ON DELETE RESTRICT, UNIQUE KEY uq_product_image_order(product_id,sort_order)
);
CREATE TABLE product_skin_type (
 product_id VARCHAR(64) NOT NULL, skin_type_code VARCHAR(32) NOT NULL, PRIMARY KEY(product_id,skin_type_code),
 FOREIGN KEY(product_id) REFERENCES product(product_id) ON DELETE CASCADE, FOREIGN KEY(skin_type_code) REFERENCES skin_type(code)
);
CREATE TABLE product_concern (
 product_id VARCHAR(64) NOT NULL, concern_code VARCHAR(64) NOT NULL, PRIMARY KEY(product_id,concern_code),
 FOREIGN KEY(product_id) REFERENCES product(product_id) ON DELETE CASCADE, FOREIGN KEY(concern_code) REFERENCES concern(code)
);
CREATE TABLE clean_feature (code VARCHAR(64) PRIMARY KEY, label_ko VARCHAR(100) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE);
CREATE TABLE texture_feature (code VARCHAR(64) PRIMARY KEY, label_ko VARCHAR(100) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE);
CREATE TABLE product_clean (
 product_id VARCHAR(64) NOT NULL, clean_code VARCHAR(64) NOT NULL, PRIMARY KEY(product_id,clean_code),
 FOREIGN KEY(product_id) REFERENCES product(product_id) ON DELETE CASCADE, FOREIGN KEY(clean_code) REFERENCES clean_feature(code)
);
CREATE TABLE product_texture (
 product_id VARCHAR(64) NOT NULL, texture_code VARCHAR(64) NOT NULL, PRIMARY KEY(product_id,texture_code),
 FOREIGN KEY(product_id) REFERENCES product(product_id) ON DELETE CASCADE, FOREIGN KEY(texture_code) REFERENCES texture_feature(code)
);
CREATE TABLE ingredient (ingredient_code VARCHAR(64) PRIMARY KEY, label_ko TEXT NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE);
CREATE TABLE product_ingredient (
 product_id VARCHAR(64) NOT NULL, ingredient_code VARCHAR(64) NOT NULL, first_position INT NULL, weight DECIMAL(8,6) NULL, parser_version VARCHAR(32) NOT NULL,
 PRIMARY KEY(product_id,ingredient_code), FOREIGN KEY(product_id) REFERENCES product(product_id) ON DELETE CASCADE, FOREIGN KEY(ingredient_code) REFERENCES ingredient(ingredient_code)
);
CREATE TABLE cart (
 cart_id VARCHAR(64) PRIMARY KEY, member_id VARCHAR(64) NOT NULL UNIQUE, created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
 FOREIGN KEY(member_id) REFERENCES member(member_id) ON DELETE RESTRICT
);
CREATE TABLE cart_item (
 cart_item_id VARCHAR(64) PRIMARY KEY, cart_id VARCHAR(64) NOT NULL, variant_id VARCHAR(64) NOT NULL, quantity INT NOT NULL,
 FOREIGN KEY(cart_id) REFERENCES cart(cart_id) ON DELETE CASCADE, FOREIGN KEY(variant_id) REFERENCES product_variant(variant_id) ON DELETE RESTRICT, UNIQUE KEY uq_cart_variant(cart_id,variant_id), CHECK(quantity > 0)
);
CREATE TABLE shop_order (
 order_id VARCHAR(64) PRIMARY KEY, member_id VARCHAR(64) NOT NULL, idempotency_key VARCHAR(128) NOT NULL, request_hash CHAR(64) NOT NULL,
 status ENUM('CREATED','PAID','CANCELLED','REFUNDED') NOT NULL DEFAULT 'CREATED', currency CHAR(3) NOT NULL DEFAULT 'KRW', total_amount DECIMAL(18,0) NOT NULL, paid_at DATETIME(6) NULL,
 created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
 FOREIGN KEY(member_id) REFERENCES member(member_id) ON DELETE RESTRICT, UNIQUE KEY uq_order_idempotency(member_id,idempotency_key), CHECK(total_amount >= 0), INDEX ix_order_member_created(member_id,created_at)
);
CREATE TABLE order_item (
 order_item_id VARCHAR(64) PRIMARY KEY, order_id VARCHAR(64) NOT NULL, variant_id VARCHAR(64) NOT NULL, product_id VARCHAR(64) NOT NULL, brand_id VARCHAR(64) NOT NULL,
 product_name_snapshot VARCHAR(300) NOT NULL, brand_name_snapshot VARCHAR(200) NOT NULL, sku_snapshot VARCHAR(64) NOT NULL, variant_label_snapshot VARCHAR(200) NOT NULL, unit_price DECIMAL(18,0) NOT NULL, quantity INT NOT NULL, line_amount DECIMAL(18,0) NOT NULL,
 FOREIGN KEY(order_id) REFERENCES shop_order(order_id) ON DELETE RESTRICT, FOREIGN KEY(variant_id) REFERENCES product_variant(variant_id) ON DELETE RESTRICT, FOREIGN KEY(product_id,brand_id) REFERENCES product(product_id,brand_id) ON DELETE RESTRICT,
 UNIQUE KEY uq_order_variant(order_id,variant_id), UNIQUE KEY uq_order_item_brand(order_item_id,brand_id), CHECK(quantity > 0), CHECK(unit_price > 0), CHECK(line_amount = unit_price * quantity), INDEX ix_order_item_brand(brand_id,order_id)
);
CREATE TABLE review (
 review_id VARCHAR(64) PRIMARY KEY, order_item_id VARCHAR(64) NOT NULL UNIQUE, rating TINYINT NOT NULL, is_recommended BOOLEAN NULL, title VARCHAR(300) NULL, body TEXT NULL,
 status ENUM('PUBLISHED','HIDDEN','DELETED') NOT NULL DEFAULT 'PUBLISHED', skin_type_snapshot VARCHAR(32) NULL, skin_tone_snapshot VARCHAR(32) NULL, hair_color_snapshot VARCHAR(32) NULL, concerns_snapshot_json JSON NULL,
 created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6), FOREIGN KEY(order_item_id) REFERENCES order_item(order_item_id) ON DELETE RESTRICT, CHECK(rating BETWEEN 1 AND 5)
);
CREATE TABLE feedback (
 feedback_id VARCHAR(64) PRIMARY KEY, order_item_id VARCHAR(64) NOT NULL UNIQUE, body TEXT NOT NULL, status ENUM('VISIBLE','HIDDEN','DELETED') NOT NULL DEFAULT 'VISIBLE',
 created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6), FOREIGN KEY(order_item_id) REFERENCES order_item(order_item_id) ON DELETE RESTRICT
);
CREATE TABLE settlement (
 settlement_id VARCHAR(64) PRIMARY KEY, brand_id VARCHAR(64) NOT NULL, settlement_month DATE NOT NULL, currency CHAR(3) NOT NULL DEFAULT 'KRW', gross_amount DECIMAL(18,0) NOT NULL, fee_amount DECIMAL(18,0) NOT NULL DEFAULT 0, net_amount DECIMAL(18,0) NOT NULL,
 status ENUM('PENDING','COMPLETED') NOT NULL DEFAULT 'PENDING', completed_at DATETIME(6) NULL, completed_by VARCHAR(64) NULL, FOREIGN KEY(brand_id) REFERENCES brand(brand_id) ON DELETE RESTRICT, FOREIGN KEY(completed_by) REFERENCES admin_account(admin_account_id) ON DELETE RESTRICT,
 UNIQUE KEY uq_settlement_month(brand_id,settlement_month), UNIQUE KEY uq_settlement_brand(settlement_id,brand_id), CHECK(fee_amount = 0), CHECK(net_amount = gross_amount)
);
CREATE TABLE settlement_item (
 settlement_item_id VARCHAR(64) PRIMARY KEY, settlement_id VARCHAR(64) NOT NULL, brand_id VARCHAR(64) NOT NULL, order_item_id VARCHAR(64) NOT NULL UNIQUE, gross_amount DECIMAL(18,0) NOT NULL, fee_amount DECIMAL(18,0) NOT NULL DEFAULT 0, net_amount DECIMAL(18,0) NOT NULL,
 FOREIGN KEY(settlement_id,brand_id) REFERENCES settlement(settlement_id,brand_id) ON DELETE RESTRICT, FOREIGN KEY(order_item_id,brand_id) REFERENCES order_item(order_item_id,brand_id) ON DELETE RESTRICT, CHECK(fee_amount = 0), CHECK(net_amount = gross_amount)
);
