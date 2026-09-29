package com.cosmetic.shopbackend.commerce;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class TestPayAllowanceTest {

  @Test
  @DisplayName("PA 접두 회원(에이전트 러너)은 테스트 결제를 부를 수 있다")
  void agentRunnerAllowed() {
    assertTrue(CommerceController.testPayAllowed("PA", "PA00001"));
    assertTrue(CommerceController.testPayAllowed(" PA ", "PA00100"));
  }

  @Test
  @DisplayName("접두가 다른 회원은 막는다")
  void otherMembersDenied() {
    assertFalse(CommerceController.testPayAllowed("PA", "M00001"));
    assertFalse(CommerceController.testPayAllowed("PA", null));
  }

  @Test
  @DisplayName("접두 설정이 비어 있으면 아무도 통과하지 못한다")
  void blankPrefixDeniesEveryone() {
    assertFalse(CommerceController.testPayAllowed("", "PA00001"));
    assertFalse(CommerceController.testPayAllowed("   ", "M00001"));
    assertFalse(CommerceController.testPayAllowed(null, "PA00001"));
  }
}
