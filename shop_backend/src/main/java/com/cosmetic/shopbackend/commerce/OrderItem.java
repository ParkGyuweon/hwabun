package com.cosmetic.shopbackend.commerce;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_item")
public class OrderItem {

  @Id
  @Column(name = "order_item_id")
  private String id;

  @Column(name = "order_id")
  private String orderId;

  @Column(name = "variant_id")
  private String variantId;

  @Column(name = "product_id")
  private String productId;

  @Column(name = "brand_id")
  private String brandId;

  @Column(name = "product_name_snapshot")
  private String productName;

  @Column(name = "brand_name_snapshot")
  private String brandName = "";

  @Column(name = "sku_snapshot")
  private String sku;

  @Column(name = "variant_label_snapshot")
  private String variantLabel;

  @Column(name = "unit_price")
  private BigDecimal unitPrice;

  private int quantity;

  @Column(name = "line_amount")
  private BigDecimal lineAmount;

  protected OrderItem() {}

  public int getQuantity() {
    return quantity;
  }

  public OrderItem(
    String id,
    String orderId,
    String variantId,
    String productId,
    String brandId,
    String pn,
    String sku,
    String label,
    BigDecimal price,
    int qty
  ) {
    this(
      id,
      orderId,
      variantId,
      productId,
      brandId,
      pn,
      "",
      sku,
      label,
      price,
      qty
    );
  }

  public OrderItem(
    String id,
    String orderId,
    String variantId,
    String productId,
    String brandId,
    String pn,
    String bn,
    String sku,
    String label,
    BigDecimal price,
    int qty
  ) {
    this.id = id;
    this.orderId = orderId;
    this.variantId = variantId;
    this.productId = productId;
    this.brandId = brandId;
    productName = pn;
    brandName = bn;
    this.sku = sku;
    variantLabel = label;
    unitPrice = price;
    quantity = qty;
    lineAmount = price.multiply(BigDecimal.valueOf(qty));
  }
}
