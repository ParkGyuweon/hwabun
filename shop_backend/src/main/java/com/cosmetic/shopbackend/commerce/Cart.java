package com.cosmetic.shopbackend.commerce;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "cart")
public class Cart {

  @Id
  @Column(name = "cart_id")
  private String id;

  @Column(name = "member_id", nullable = false, unique = true)
  private String memberId;

  @Column(name = "created_at", nullable = false)
  private LocalDateTime createdAt;

  @Column(name = "updated_at", nullable = false)
  private LocalDateTime updatedAt;

  protected Cart() {}

  public Cart(String id, String m) {
    this.id = id;
    memberId = m;
  }

  public String getId() {
    return id;
  }

  public String getMemberId() {
    return memberId;
  }

  @PrePersist
  void pre() {
    LocalDateTime n = LocalDateTime.now();
    createdAt = n;
    updatedAt = n;
  }

  @PreUpdate
  void upd() {
    updatedAt = LocalDateTime.now();
  }
}
