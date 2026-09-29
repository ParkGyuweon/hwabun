package com.cosmetic.shopbackend.identity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.cosmetic.shopbackend.commerce.Cart;
import com.cosmetic.shopbackend.commerce.CartItemRepository;
import com.cosmetic.shopbackend.commerce.CartRepository;
import com.cosmetic.shopbackend.commerce.ShopOrder;
import com.cosmetic.shopbackend.commerce.ShopOrderRepository;
import com.cosmetic.shopbackend.security.JwtTokenService;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

/**
 * 회원 탈퇴. 저장소는 목록 하나를 흉내 낸 가짜(이메일로 찾기·저장)라서, 탈퇴 → 로그인 → 재가입을
 * 실제 컨트롤러 두 개(MemberAccountController, IdentityController)로 이어서 돌려 볼 수 있다.
 */
class MemberWithdrawalTest {

  private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
  private static final Instant NOW = Instant.parse("2026-09-29T03:00:00Z");

  private final List<Member> store = new ArrayList<>();
  private final PasswordEncoder encoder = new BCryptPasswordEncoder(4);
  private MemberRepository members;
  private CartRepository carts;
  private CartItemRepository cartItems;
  private ShopOrderRepository orders;
  private JwtTokenService tokens;
  private MemberAccountController account;
  private IdentityController identity;

  @BeforeEach
  void setUp() {
    members = mock(MemberRepository.class);
    when(members.findById(anyString())).thenAnswer(inv ->
      store.stream().filter(m -> m.getId().equals(inv.getArgument(0))).findFirst()
    );
    when(members.findByEmail(anyString())).thenAnswer(inv ->
      store.stream().filter(m -> m.getEmail().equals(inv.getArgument(0))).findFirst()
    );
    when(members.save(any(Member.class))).thenAnswer(inv -> {
      Member m = inv.getArgument(0);
      if (m.getId() == null) m.setId("m-" + (store.size() + 1));
      if (!store.contains(m)) store.add(m);
      return m;
    });
    carts = mock(CartRepository.class);
    cartItems = mock(CartItemRepository.class);
    orders = mock(ShopOrderRepository.class);
    tokens = new JwtTokenService("01234567890123456789012345678901", 60_000);
    MemberWithdrawalService service = new MemberWithdrawalService(
      members, encoder, carts, cartItems, orders, Clock.fixed(NOW, SEOUL)
    );
    account = new MemberAccountController(service);
    identity = new IdentityController(
      mock(SellerAccountRepository.class), members, mock(AdminAccountRepository.class), encoder, tokens
    );
  }

  private Member signedUp() {
    identity.member(new IdentityController.RegisterMember(
      "yu@example.com", "password123", "유림", "dry", "light", "black", "brown", true, true, true, true
    ));
    return store.getFirst();
  }

  private ShopPrincipal principal(Member m) {
    return new ShopPrincipal(m.getId(), AccountRole.MEMBER);
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> body(ResponseEntity<?> res) {
    return (Map<String, Object>) res.getBody();
  }

  @Test
  void withdrawAnonymisesMemberKeepsIdAndDeletesCart() {
    Member m = signedUp();
    String id = m.getId();
    when(carts.findByMemberId(id)).thenReturn(Optional.of(new Cart("cart-1", id)));

    ResponseEntity<?> res = account.withdraw(principal(m), new MemberAccountController.WithdrawRequest("password123"));

    assertEquals(204, res.getStatusCode().value());
    assertEquals(id, m.getId());
    assertEquals(AccountStatus.WITHDRAWN, m.getStatus());
    assertEquals(LocalDateTime.ofInstant(NOW, SEOUL), m.getWithdrawnAt());
    assertEquals("withdrawn+" + id + "@deleted.invalid", m.getEmail());
    assertEquals("탈퇴한 회원", m.getNickname());
    assertNull(m.getSkinTypeCode());
    assertNull(m.getSkinToneCode());
    assertNull(m.getHairColorCode());
    assertNull(m.getEyeColorCode());
    assertFalse(encoder.matches("password123", m.getPasswordHash()));
    verify(cartItems).deleteByCartId("cart-1");
    verify(carts).delete(any(Cart.class));
    // 주문은 조회(차단 판정)만 하고 지우거나 고치지 않는다
    verify(orders, never()).delete(any());
    verify(orders, never()).deleteAll();
  }

  @Test
  void wrongPasswordIs403WithFriendlyMessageAndChangesNothing() {
    Member m = signedUp();

    ResponseEntity<?> res = account.withdraw(principal(m), new MemberAccountController.WithdrawRequest("nope-nope"));

    assertEquals(403, res.getStatusCode().value());
    assertEquals("wrong_password", body(res).get("error"));
    assertEquals("비밀번호가 맞지 않아요.", body(res).get("message"));
    assertEquals(AccountStatus.ACTIVE, m.getStatus());
    assertEquals("yu@example.com", m.getEmail());
    verify(carts, never()).delete(any(Cart.class));
  }

  @Test
  void missingPasswordIs400() {
    Member m = signedUp();

    ResponseEntity<?> noBody = account.withdraw(principal(m), null);
    ResponseEntity<?> blank = account.withdraw(principal(m), new MemberAccountController.WithdrawRequest(" "));

    assertEquals(400, noBody.getStatusCode().value());
    assertEquals("password_required", body(noBody).get("error"));
    assertEquals(400, blank.getStatusCode().value());
    assertEquals(AccountStatus.ACTIVE, m.getStatus());
  }

  @Test
  void orderAwaitingPaymentConfirmationBlocksWithdrawWith409() {
    Member m = signedUp();
    when(orders.existsByMemberIdAndStatusAndCreatedAtAfter(
      eq(m.getId()), eq(ShopOrder.Status.CREATED), eq(LocalDateTime.ofInstant(NOW, SEOUL).minusMinutes(30))
    )).thenReturn(true);

    ResponseEntity<?> res = account.withdraw(principal(m), new MemberAccountController.WithdrawRequest("password123"));

    assertEquals(409, res.getStatusCode().value());
    assertEquals("order_in_progress", body(res).get("error"));
    assertEquals(
      "처리 중인 주문이 있어 지금은 탈퇴할 수 없어요. 주문이 끝난 뒤 다시 시도해 주세요.",
      body(res).get("message")
    );
    assertEquals(AccountStatus.ACTIVE, m.getStatus());
  }

  @Test
  void sellerTokenCannotWithdrawAndAnonymousIs401() {
    ResponseEntity<?> seller = account.withdraw(
      new ShopPrincipal("s-1", AccountRole.SELLER), new MemberAccountController.WithdrawRequest("password123")
    );
    ResponseEntity<?> anonymous = account.withdraw(null, new MemberAccountController.WithdrawRequest("password123"));

    assertEquals(403, seller.getStatusCode().value());
    assertEquals(401, anonymous.getStatusCode().value());
  }

  @Test
  void loginAfterWithdrawFailsAndSameEmailCanSignUpAgain() {
    Member old = signedUp();
    account.withdraw(principal(old), new MemberAccountController.WithdrawRequest("password123"));

    var byOriginalEmail = identity.login(new IdentityController.Login("yu@example.com", "password123", AccountRole.MEMBER));
    var byPlaceholder = identity.login(new IdentityController.Login(old.getEmail(), "password123", AccountRole.MEMBER));
    assertEquals(401, byOriginalEmail.getStatusCode().value());
    assertEquals(401, byPlaceholder.getStatusCode().value());

    var again = identity.member(new IdentityController.RegisterMember(
      "yu@example.com", "password456", "유림2", null, null, null, null, true, true, null, null
    ));
    assertEquals(201, again.getStatusCode().value());
    assertNotNull(again.getBody());
    assertNotEquals(old.getId(), ((IdentityController.AccountResponse) again.getBody()).id());

    var login = identity.login(new IdentityController.Login("yu@example.com", "password456", AccountRole.MEMBER));
    assertEquals(200, login.getStatusCode().value());
    assertEquals(((IdentityController.AccountResponse) again.getBody()).id(), ((IdentityController.AccountResponse) login.getBody()).id());
  }

  @Test
  void secondWithdrawOfSameMemberIsRejected() {
    Member m = signedUp();
    account.withdraw(principal(m), new MemberAccountController.WithdrawRequest("password123"));

    ResponseEntity<?> res = account.withdraw(principal(m), new MemberAccountController.WithdrawRequest("password123"));

    assertEquals(401, res.getStatusCode().value());
    assertTrue(m.getEmail().endsWith("@deleted.invalid"));
  }
}
