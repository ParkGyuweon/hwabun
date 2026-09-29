package com.cosmetic.shopbackend.identity;

import jakarta.persistence.*;
import java.time.LocalDateTime;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Entity
@Table(name = "member")
@Getter
@Setter
@NoArgsConstructor
public class Member {

  @Id
  @Column(name = "member_id", length = 64)
  private String id;

  @Column(nullable = false, unique = true, length = 320)
  private String email;

  @Column(name = "password_hash", nullable = false)
  private String passwordHash;

  @Column(nullable = false, length = 100)
  private String nickname;

  @Column(name = "skin_type_code", length = 64)
  private String skinTypeCode;
  @Column(name = "skin_tone_code", length = 64)
  private String skinToneCode;
  @Column(name = "hair_color_code", length = 64)
  private String hairColorCode;
  @Column(name = "eye_color_code", length = 64)
  private String eyeColorCode;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false)
  private AccountStatus status = AccountStatus.ACTIVE;

  /** 탈퇴 시각. 탈퇴하지 않은 회원은 NULL */
  @Column(name = "withdrawn_at")
  private LocalDateTime withdrawnAt;

  @Column(name = "created_at", nullable = false)
  private LocalDateTime createdAt;

  @Column(name = "updated_at", nullable = false)
  private LocalDateTime updatedAt;

  @PrePersist
  void prePersist() {
    if (id == null) id = java.util.UUID.randomUUID().toString();
    createdAt = LocalDateTime.now();
    updatedAt = createdAt;
  }

  @PreUpdate
  void preUpdate() {
    updatedAt = LocalDateTime.now();
  }
}
