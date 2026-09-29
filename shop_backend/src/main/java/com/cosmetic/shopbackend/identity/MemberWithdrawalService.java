package com.cosmetic.shopbackend.identity;

import com.cosmetic.shopbackend.commerce.CartItemRepository;
import com.cosmetic.shopbackend.commerce.CartRepository;
import com.cosmetic.shopbackend.commerce.ShopOrder;
import com.cosmetic.shopbackend.commerce.ShopOrderRepository;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Base64;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 회원 탈퇴 — 행은 지우지 않고(soft delete) 개인정보만 지운다.
 *
 * 남기는 것: member 행(member_id 그대로), 주문·결제·주문 품목·정산 품목·리뷰·의견·알림.
 *   거래·이용 기록은 5년 보존한다(제품 결정). member_id 를 바꾸지 않는 이유는 이 행들이 모두 member_id 로
 *   묶여 있고(FK RESTRICT), 테스트 결제 허용 접두(`shop.test-pay.allowed-member-prefix`)도 member_id 로 판정하기 때문이다.
 *
 * 지우는 것: 이메일(→ 배달 불가 자리표시자, 같은 이메일로 다시 가입할 수 있게), 닉네임(→ "탈퇴한 회원"),
 *   피부 프로필 네 칸, 비밀번호 해시(→ 어떤 입력과도 맞지 않는 값), 장바구니(cart + cart_item).
 *
 * 탈퇴를 막는 주문: 결제창을 연 뒤 아직 확정되지 않았을 수 있는 주문 — 상태 CREATED 이고
 *   {@link #PAYMENT_IN_FLIGHT} 안에 만든 것. PortOne 에서 돈은 나갔는데 `/confirm` 이 아직 안 온 경우,
 *   탈퇴하면 토큰이 막혀 그 주문을 영영 확정할 수 없다. 이 시스템의 주문 상태는 CREATED·PAID·CANCELLED·REFUNDED
 *   뿐이고 배송·반품 단계가 없어서 PAID·CANCELLED·REFUNDED 는 모두 끝난 주문이다. 오래된 CREATED 는 결제를
 *   포기한 주문이라(취소 API 가 없어 그대로 남는다) 막지 않는다 — 막으면 영영 탈퇴할 수 없다.
 *   배송·환불 요청 같은 진행 상태가 생기면 여기에 더한다.
 */
@Service
public class MemberWithdrawalService {

  public static final String WITHDRAWN_NICKNAME = "탈퇴한 회원";
  static final String WITHDRAWN_EMAIL_DOMAIN = "@deleted.invalid";
  /** 결제창을 연 주문이 아직 확정 중일 수 있다고 보는 시간 */
  static final Duration PAYMENT_IN_FLIGHT = Duration.ofMinutes(30);
  private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
  private static final SecureRandom RANDOM = new SecureRandom();

  private final MemberRepository members;
  private final PasswordEncoder encoder;
  private final CartRepository carts;
  private final CartItemRepository cartItems;
  private final ShopOrderRepository orders;
  private final Clock clock;

  @Autowired
  public MemberWithdrawalService(
    MemberRepository members,
    PasswordEncoder encoder,
    CartRepository carts,
    CartItemRepository cartItems,
    ShopOrderRepository orders
  ) {
    this(members, encoder, carts, cartItems, orders, Clock.system(SEOUL));
  }

  MemberWithdrawalService(
    MemberRepository members,
    PasswordEncoder encoder,
    CartRepository carts,
    CartItemRepository cartItems,
    ShopOrderRepository orders,
    Clock clock
  ) {
    this.members = members;
    this.encoder = encoder;
    this.carts = carts;
    this.cartItems = cartItems;
    this.orders = orders;
    this.clock = clock;
  }

  /** 탈퇴를 거절한 이유. 컨트롤러가 {"error": code, "message": message} 로 내보낸다 */
  public static class Rejected extends RuntimeException {

    private final HttpStatus status;
    private final String code;

    Rejected(HttpStatus status, String code, String message) {
      super(message);
      this.status = status;
      this.code = code;
    }

    public HttpStatus status() {
      return status;
    }

    public String code() {
      return code;
    }
  }

  @Transactional
  public void withdraw(String memberId, String password) {
    if (password == null || password.isBlank()) {
      throw new Rejected(HttpStatus.BAD_REQUEST, "password_required", "비밀번호를 입력해 주세요.");
    }
    Member member = members
      .findById(memberId)
      .filter(m -> m.getStatus() == AccountStatus.ACTIVE)
      .orElseThrow(() ->
        new Rejected(HttpStatus.UNAUTHORIZED, "unauthorized", "다시 로그인해 주세요.")
      );
    if (!passwordMatches(member.getPasswordHash(), password)) {
      throw new Rejected(HttpStatus.FORBIDDEN, "wrong_password", "비밀번호가 맞지 않아요.");
    }
    LocalDateTime now = LocalDateTime.now(clock);
    if (
      orders.existsByMemberIdAndStatusAndCreatedAtAfter(
        memberId,
        ShopOrder.Status.CREATED,
        now.minus(PAYMENT_IN_FLIGHT)
      )
    ) {
      throw new Rejected(
        HttpStatus.CONFLICT,
        "order_in_progress",
        "처리 중인 주문이 있어 지금은 탈퇴할 수 없어요. 주문이 끝난 뒤 다시 시도해 주세요."
      );
    }

    carts
      .findByMemberId(memberId)
      .ifPresent(cart -> {
        cartItems.deleteByCartId(cart.getId());
        carts.delete(cart);
      });

    member.setStatus(AccountStatus.WITHDRAWN);
    member.setWithdrawnAt(now);
    member.setEmail(withdrawnEmail(memberId));
    member.setNickname(WITHDRAWN_NICKNAME);
    member.setSkinTypeCode(null);
    member.setSkinToneCode(null);
    member.setHairColorCode(null);
    member.setEyeColorCode(null);
    member.setPasswordHash(unusablePasswordHash());
    members.save(member);
  }

  /** member_id 는 PK 라 겹치지 않는다. `.invalid` 는 배달되지 않는 예약 도메인(RFC 2606). 최대 64+26자 < 320 */
  static String withdrawnEmail(String memberId) {
    return "withdrawn+" + memberId + WITHDRAWN_EMAIL_DOMAIN;
  }

  /**
   * BCrypt(`$2a$…`)도 SHA-256 16진수 64자도 아닌 값이라 어떤 비밀번호와도 맞지 않는다.
   * 로그인은 그 전에 status 로 이미 거절한다 — 이것은 두 번째 잠금이다.
   */
  private static String unusablePasswordHash() {
    byte[] bytes = new byte[24];
    RANDOM.nextBytes(bytes);
    return "!withdrawn!" + Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
  }

  private boolean passwordMatches(String stored, String submitted) {
    if (stored == null) return false;
    if (PasswordHashes.isLegacySha256(stored)) return PasswordHashes.legacyMatches(stored, submitted);
    return encoder.matches(submitted, stored);
  }
}
