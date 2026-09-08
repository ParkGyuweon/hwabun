package com.cosmetic.shopbackend.brand;
import com.cosmetic.shopbackend.identity.SellerAccount; import jakarta.persistence.*; import lombok.*; import java.time.LocalDateTime;
@Entity @Table(name="brand", uniqueConstraints=@UniqueConstraint(name="uq_brand_seller_name",columnNames={"seller_account_id","name"})) @Getter @Setter @NoArgsConstructor
public class Brand {
 @Id @Column(name="brand_id",length=64) private String id;
 @ManyToOne(fetch=FetchType.LAZY,optional=false) @JoinColumn(name="seller_account_id",nullable=false) private SellerAccount seller;
 @Column(nullable=false,length=200) private String name; @Column(columnDefinition="TEXT") private String description; @Column(name="logo_url",length=1000) private String logoUrl;
 @Enumerated(EnumType.STRING) @Column(nullable=false) private BrandStatus status=BrandStatus.ACTIVE; @Column(name="created_at",nullable=false) private LocalDateTime createdAt; @Column(name="updated_at",nullable=false) private LocalDateTime updatedAt;
 @PrePersist void pre(){if(id==null)id=java.util.UUID.randomUUID().toString();createdAt=LocalDateTime.now();updatedAt=createdAt;} @PreUpdate void upd(){updatedAt=LocalDateTime.now();}
}
