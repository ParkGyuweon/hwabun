package com.cosmetic.shopbackend.catalog;
import jakarta.persistence.*; import java.math.BigDecimal;
@Entity @Table(name="product_variant") public class ProductVariant {
 @Id @Column(name="variant_id") private String id; @Column(name="product_id",nullable=false) private String productId; @Column(name="sku_id",nullable=false,unique=true) private String sku;
 @Column(nullable=false) private String label; private String size; @Column(name="price_krw",nullable=false) private BigDecimal price; @Column(name="sale_price_krw") private BigDecimal salePrice;
 @Enumerated(EnumType.STRING) @Column(nullable=false) private Status status=Status.ACTIVE; @Column(name="sort_order") private int sortOrder;
 protected ProductVariant(){} public ProductVariant(String id,String productId,String sku,String label,BigDecimal price,BigDecimal salePrice){this.id=id;this.productId=productId;this.sku=sku;this.label=label;this.price=price;this.salePrice=salePrice;}
 public String getId(){return id;} public String getProductId(){return productId;} public String getSku(){return sku;} public String getLabel(){return label;} public String getSize(){return size;} public BigDecimal getPrice(){return price;} public BigDecimal getSalePrice(){return salePrice;} public BigDecimal unitPrice(){return salePrice!=null?salePrice:price;} public Status getStatus(){return status;}
 public void updateBasePrice(BigDecimal value){this.price=value;}
 public enum Status{ACTIVE,INACTIVE}
}
