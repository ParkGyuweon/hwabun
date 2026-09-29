package com.cosmetic.shopbackend.identity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.cosmetic.shopbackend.security.JwtTokenService;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.password.PasswordEncoder;

class LoginAttemptLimiterTest {

  @Test
  @DisplayName("10분 안에 10번 틀리면 막고, 창이 지나면 풀린다")
  void blocksAfterMaxFailuresWithinWindow() {
    AtomicLong now = new AtomicLong(0);
    LoginAttemptLimiter limiter = new LoginAttemptLimiter(10, 600_000, now::get);
    String key = LoginAttemptLimiter.key(AccountRole.MEMBER, "A@Example.com");
    for (int i = 0; i < 9; i++) limiter.recordFailure(key);
    assertFalse(limiter.blocked(key));
    limiter.recordFailure(key);
    assertTrue(limiter.blocked(key));
    assertTrue(
      limiter.blocked(LoginAttemptLimiter.key(AccountRole.MEMBER, " a@example.com "))
    );
    assertFalse(
      limiter.blocked(LoginAttemptLimiter.key(AccountRole.SELLER, "a@example.com"))
    );
    now.set(600_000);
    assertFalse(limiter.blocked(key));
  }

  @Test
  @DisplayName("성공하면 실패 기록을 지운다")
  void resetClearsFailures() {
    LoginAttemptLimiter limiter = new LoginAttemptLimiter(3, 600_000, () -> 0);
    String key = LoginAttemptLimiter.key(AccountRole.MEMBER, "a@example.com");
    limiter.recordFailure(key);
    limiter.recordFailure(key);
    limiter.reset(key);
    limiter.recordFailure(key);
    limiter.recordFailure(key);
    assertFalse(limiter.blocked(key));
  }

  @Test
  @DisplayName("로그인을 10번 틀리면 맞는 비밀번호도 429, 다른 계정은 그대로 로그인된다")
  void controllerReturns429AfterTenFailures() {
    MemberRepository members = mock(MemberRepository.class);
    PasswordEncoder encoder = mock(PasswordEncoder.class);
    JwtTokenService tokens = mock(JwtTokenService.class);
    Member victim = member("M1", "victim@example.com");
    Member agent = member("PA00001", "pa00001@example.com");
    when(members.findByEmail("victim@example.com")).thenReturn(Optional.of(victim));
    when(members.findByEmail("pa00001@example.com")).thenReturn(Optional.of(agent));
    when(encoder.matches("right-password", "hash")).thenReturn(true);
    when(encoder.matches("wrong", "hash")).thenReturn(false);
    when(tokens.issue(anyString(), any(AccountRole.class), any())).thenReturn("t");
    IdentityController controller = new IdentityController(
      mock(SellerAccountRepository.class),
      members,
      mock(AdminAccountRepository.class),
      encoder,
      tokens
    );

    for (int i = 0; i < 10; i++) assertEquals(
      401,
      controller.login(login("victim@example.com", "wrong")).getStatusCode().value()
    );
    ResponseEntity<?> blocked = controller.login(
      login("victim@example.com", "right-password")
    );
    assertEquals(429, blocked.getStatusCode().value());
    assertEquals(
      IdentityController.TOO_MANY_ATTEMPTS_MESSAGE,
      ((Map<?, ?>) blocked.getBody()).get("message")
    );
    assertEquals(
      200,
      controller.login(login("pa00001@example.com", "right-password")).getStatusCode().value()
    );
  }

  @Test
  @DisplayName("성공한 로그인은 실패 횟수를 되돌린다")
  void successResetsCounterInController() {
    MemberRepository members = mock(MemberRepository.class);
    PasswordEncoder encoder = mock(PasswordEncoder.class);
    Member m = member("M1", "m@example.com");
    when(members.findByEmail("m@example.com")).thenReturn(Optional.of(m));
    when(encoder.matches("right-password", "hash")).thenReturn(true);
    IdentityController controller = new IdentityController(
      mock(SellerAccountRepository.class),
      members,
      mock(AdminAccountRepository.class),
      encoder,
      mock(JwtTokenService.class)
    );
    for (int i = 0; i < 9; i++) controller.login(login("m@example.com", "wrong"));
    assertEquals(
      200,
      controller.login(login("m@example.com", "right-password")).getStatusCode().value()
    );
    for (int i = 0; i < 9; i++) controller.login(login("m@example.com", "wrong"));
    assertEquals(
      200,
      controller.login(login("m@example.com", "right-password")).getStatusCode().value()
    );
  }

  private static Member member(String id, String email) {
    Member m = new Member();
    m.setId(id);
    m.setEmail(email);
    m.setNickname(id);
    m.setPasswordHash("hash");
    return m;
  }

  private static IdentityController.Login login(String email, String password) {
    return new IdentityController.Login(email, password, AccountRole.MEMBER);
  }
}
