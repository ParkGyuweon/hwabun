package com.cosmetic.shopbackend.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.*;

@Entity @Table(name="product")
public class Product {
 @Id @Column(name="product_id",length=64) private String id;
 @Column(name="brand_id",nullable=false) private String brandId;
 @Column(name="category_id",nullable=false) private String categoryId;
 @Column(name="product_name",nullable=false) private String name;
 @Enumerated(EnumType.STRING) @Column(name="product_source",nullable=false) private Source productSource=Source.brand_registered;
 @Enumerated(EnumType.STRING) @Column(nullable=false) private Status status=Status.DRAFT;
 @Column(name="secondary_category",nullable=false) private String secondaryCategory;
 @Column(name="tertiary_category",nullable=false) private String tertiaryCategory;
 @Column(name="price_bin",nullable=false) private String priceBin;
 @Column(precision=4,scale=2) private BigDecimal rating;
 @Column(name="loves_count") private Integer lovesCount;
 @Column(name="primary_image_url") private String primaryImageUrl;
 @Column(name="description_json",columnDefinition="json") private String descriptionJson;
 @Column(name="ingredients_text",columnDefinition="text") private String ingredientsText;
 @Column(name="source_price_usd",precision=12,scale=2) private BigDecimal priceUsd;
 @Column(name="source_rating",precision=4,scale=2) private BigDecimal sourceRating;
 @Column(name="source_loves_count") private Integer sourceLovesCount;
 @Column(name="created_at") private LocalDateTime createdAt; @Column(name="updated_at") private LocalDateTime updatedAt;
 @ElementCollection @CollectionTable(name="product_concern",joinColumns=@JoinColumn(name="product_id")) @Column(name="concern_code") private Set<String> concerns=new LinkedHashSet<>();
 @ElementCollection @CollectionTable(name="product_clean",joinColumns=@JoinColumn(name="product_id")) @Column(name="clean_code") private Set<String> cleanFeatures=new LinkedHashSet<>();
 @ElementCollection @CollectionTable(name="product_texture",joinColumns=@JoinColumn(name="product_id")) @Column(name="texture_code") private Set<String> textures=new LinkedHashSet<>();
 protected Product(){}
 public Product(String id,String brandId,String categoryId,String name){this.id=id;this.brandId=brandId;this.categoryId=categoryId;this.name=name;}
 public void update(ProductContract.ProductInput i,BigDecimal defaultRating){name=i.productName();categoryId=i.categoryId();secondaryCategory=i.secondaryCategory();tertiaryCategory=i.tertiaryCategory();priceUsd=ProductContract.usd(i.priceKrw());priceBin=ProductContract.priceBin(priceUsd);primaryImageUrl=i.primaryImageUrl();descriptionJson=i.descriptionJson();ingredientsText=i.ingredients();rating=defaultRating;sourceRating=defaultRating;lovesCount=0;sourceLovesCount=0;concerns=ProductContract.group(i.highlights(),ProductContract.CONCERNS);cleanFeatures=ProductContract.group(i.highlights(),ProductContract.CLEAN);textures=ProductContract.group(i.highlights(),ProductContract.TEXTURES);}
 public String getId(){return id;} public String getBrandId(){return brandId;} public String getCategoryId(){return categoryId;} public String getName(){return name;} public Source getProductSource(){return productSource;} public Status getStatus(){return status;} public String getSecondaryCategory(){return secondaryCategory;} public String getTertiaryCategory(){return tertiaryCategory;} public String getPriceBin(){return priceBin;} public BigDecimal getRating(){return rating;} public Integer getLovesCount(){return lovesCount;} public String getPrimaryImageUrl(){return primaryImageUrl;} public String getDescriptionJson(){return descriptionJson;} public String getIngredientsText(){return ingredientsText;} public BigDecimal getPriceUsd(){return priceUsd;} public Set<String> getHighlights(){Set<String> s=new LinkedHashSet<>(concerns);s.addAll(cleanFeatures);s.addAll(textures);return s;} public Set<String> getConcerns(){return concerns;} public Set<String> getCleanFeatures(){return cleanFeatures;} public Set<String> getTextures(){return textures;}
 public void status(Status s){status=s;} @PrePersist void pre(){LocalDateTime n=LocalDateTime.now();createdAt=n;updatedAt=n;} @PreUpdate void upd(){updatedAt=LocalDateTime.now();}
 public enum Source{seed_catalog,brand_registered} public enum Status{DRAFT,PENDING_APPROVAL,ACTIVE,INACTIVE,REJECTED}
}
