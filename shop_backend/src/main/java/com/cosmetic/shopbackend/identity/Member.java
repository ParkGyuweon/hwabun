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

  /**
   * 가입 동의 기록. 필수(이용약관·개인정보)는 동의한 시각, 선택(피부 정보·둘러본 기록 연결)은
   * 동의했을 때만 시각이 남고 아니면 null 이다. consent_version 은 그때 보여 준 약관 판.
   * 이 컬럼들이 생기기 전에 가입한 회원(시드·PA 페르소나 포함)은 전부 null 이다.
   */
  @Column(name = "terms_agreed_at")
  private LocalDateTime termsAgreedAt;
  @Column(name = "privacy_agreed_at")
  private LocalDateTime privacyAgreedAt;
  @Column(name = "skin_info_agreed_at")
  private LocalDateTime skinInfoAgreedAt;
  @Column(name = "behavior_link_agreed_at")
  private LocalDateTime behaviorLinkAgreedAt;
  @Column(name = "consent_version", length = 32)
  private String consentVersion;

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

  /**
   * 둘러본 기록을 이 계정과 이어도 되나. 가입 때 동의 화면을 거쳤는데(consent_version 있음) 연결에
   * 동의하지 않은 경우에만 false 다. 동의 컬럼이 생기기 전 계정(시드·PA 페르소나)은 지금처럼 이어진다.
   */
  public boolean isBehaviorLinked() {
    return consentVersion == null || behaviorLinkAgreedAt != null;
  }

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
