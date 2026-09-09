package com.cosmetic.shopbackend.catalog;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(
  name = "product_unmapped_value",
  uniqueConstraints = @UniqueConstraint(
    name = "uq_product_unmapped",
    columnNames = { "product_id", "field_name", "raw_value" }
  )
)
public class ProductUnmappedValue {

  @Id
  @Column(name = "unmapped_id", length = 64)
  private String id;

  @Column(name = "product_id", nullable = false)
  private String productId;

  @Column(name = "field_name", nullable = false, length = 64)
  private String fieldName;

  @Column(name = "raw_value", nullable = false, length = 255)
  private String rawValue;

  @Column(name = "created_at", nullable = false)
  private LocalDateTime createdAt;

  protected ProductUnmappedValue() {}

  public ProductUnmappedValue(
    String productId,
    String fieldName,
    String rawValue
  ) {
    this.id = java.util.UUID.randomUUID().toString();
    this.productId = productId;
    this.fieldName = fieldName;
    this.rawValue = rawValue;
  }

  @PrePersist
  void pre() {
    createdAt = LocalDateTime.now();
  }
}
