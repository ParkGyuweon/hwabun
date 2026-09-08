package com.cosmetic.shopbackend.identity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import java.time.LocalDateTime;

@Entity @Table(name="seller_account") @Getter @Setter @NoArgsConstructor
public class SellerAccount {
 @Id @Column(name="seller_account_id", length=64) private String id;
 @Column(nullable=false, unique=true, length=320) private String email;
 @Column(name="password_hash", nullable=false) private String passwordHash;
 @Column(nullable=false, length=100) private String name;
 @Enumerated(EnumType.STRING) @Column(nullable=false) private AccountStatus status=AccountStatus.ACTIVE;
 @Column(name="created_at", nullable=false) private LocalDateTime createdAt;
 @Column(name="updated_at", nullable=false) private LocalDateTime updatedAt;
 @PrePersist void prePersist(){ if(id==null) id=java.util.UUID.randomUUID().toString(); createdAt=LocalDateTime.now(); updatedAt=createdAt; }
 @PreUpdate void preUpdate(){ updatedAt=LocalDateTime.now(); }
}
