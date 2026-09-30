package com.cosmetic.shopbackend.identity;

import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 회원 탈퇴.
 *
 *   DELETE /api/members/me   { "password": "..." }   (MEMBER JWT)
 *     204 탈퇴 완료 (본문 없음)
 *     400 {"error":"password_required","message":"비밀번호를 입력해 주세요."}   본문·비밀번호 없음
 *     401 {"error":"unauthorized"}                                           토큰 없음·만료·이미 탈퇴 (보안 필터)
 *     403 {"error":"forbidden","message":"회원만 탈퇴할 수 있어요."}             판매자·관리자 토큰
 *     403 {"error":"wrong_password","message":"비밀번호가 맞지 않아요."}
 *     409 {"error":"order_in_progress","message":"처리 중인 주문이 있어 …"}      결제 확정 중인 주문
 *
 * 비밀번호가 틀렸을 때 401 이 아니라 403 인 이유: 이 경로의 401 은 "토큰이 무효" 로 읽혀야 한다.
 * 오타 한 번에 프론트가 세션을 지우면 안 된다.
 *
 * 오류는 ResponseStatusException(→ /error) 대신 본문을 직접 돌려준다. ApiExceptionHandler 와 같은
 * {"error","message"} 모양이 그대로 나간다. /api/auth/** 는 permitAll 이라 거기 두지 않았다.
 */
@RestController
@RequestMapping("/api/members/me")
public class MemberAccountController {

  private final MemberWithdrawalService withdrawals;

  public MemberAccountController(MemberWithdrawalService withdrawals) {
    this.withdrawals = withdrawals;
  }

  public record WithdrawRequest(String password) {}

  @DeleteMapping
  public ResponseEntity<?> withdraw(
    @AuthenticationPrincipal ShopPrincipal actor,
    @RequestBody(required = false) WithdrawRequest req
  ) {
    if (actor == null) {
      return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("error", "unauthorized"));
    }
    if (actor.role() != AccountRole.MEMBER) {
      return error(HttpStatus.FORBIDDEN, "forbidden", "회원만 탈퇴할 수 있어요.");
    }
    try {
      withdrawals.withdraw(actor.accountId(), req == null ? null : req.password());
    } catch (MemberWithdrawalService.Rejected rejected) {
      return error(rejected.status(), rejected.code(), rejected.getMessage());
    }
    return ResponseEntity.noContent().build();
  }

  private static ResponseEntity<Map<String, Object>> error(HttpStatus status, String code, String message) {
    return ResponseEntity.status(status).body(Map.of("error", code, "message", message));
  }
}
