package com.cosmetic.shopbackend.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.*;

@Entity @Table(name="product")
public class Product {
 @Id @Column(name="product_id", length=64) private String id;
 @Column(name="brand_id", nullable=false) private String brandId;
 @Column(name="category_id", nullable=false) private String categoryId;
 @Column(name="product_name", nullable=false) private String name;
 @Enumerated(EnumType.STRING) @Column(nullable=false) private Source productSource=Source.brand_registered;
 @Enumerated(EnumType.STRING) @Column(nullable=false) private Status status=Status.DRAFT;
 @Column(name="secondary_category",nullable=false) private String secondaryCategory="";
 @Column(name="tertiary_category",nullable=false) private String tertiaryCategory="";
 @Column(name="price_bin",nullable=false) private String priceBin="";
 @Column(name="primary_image_url") private String primaryImageUrl;
 @Column(name="created_at") private LocalDateTime createdAt; @Column(name="updated_at") private LocalDateTime updatedAt;
 protected Product() {}
 public Product(String id,String brandId,String categoryId,String name){this.id=id;this.brandId=brandId;this.categoryId=categoryId;this.name=name;}
 public String getId(){return id;} public String getBrandId(){return brandId;} public String getCategoryId(){return categoryId;} public String getName(){return name;} public Status getStatus(){return status;}
 public void update(String name,String categoryId,String image){this.name=name;this.categoryId=categoryId;this.primaryImageUrl=image;}
 public void status(Status s){this.status=s;} @PrePersist void pre(){LocalDateTime n=LocalDateTime.now();createdAt=n;updatedAt=n;} @PreUpdate void upd(){updatedAt=LocalDateTime.now();}
 public enum Source { seed_catalog, brand_registered } public enum Status { DRAFT,PENDING_APPROVAL,ACTIVE,INACTIVE,REJECTED }
}
