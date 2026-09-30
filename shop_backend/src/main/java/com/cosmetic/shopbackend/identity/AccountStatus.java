package com.cosmetic.shopbackend.identity;

public enum AccountStatus {
  ACTIVE,
  INACTIVE,
  LOCKED,
  /**
   * 회원 탈퇴 (member 만 쓴다). 행은 주문·리뷰·정산 보존(5년)을 위해 남기고, 개인정보만 지운다.
   * seller_account·admin_account 의 DB ENUM 에는 없는 값이다 — 두 계정에는 넣지 않는다.
   */
  WITHDRAWN,
}
