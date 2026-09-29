package com.cosmetic.shopbackend.identity;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.LongSupplier;

/**
 * 로그인 실패 횟수 제한 (메모리, 서버 한 대 기준).
 *
 * (역할, 이메일) 마다 최근 {@code window} 안의 실패 시각을 들고 있다가 {@code maxFailures} 번이 차면
 * 그 창이 지날 때까지 막는다. 성공하면 그 키의 기록을 지운다. 재시작하면 기록은 사라진다 — 무차별
 * 대입을 늦추는 용도라 그걸로 충분하다.
 *
 * 에이전트 러너(PA00001~PA00100)는 계정마다 한 번씩 맞는 비밀번호로 로그인하므로 걸리지 않는다.
 */
class LoginAttemptLimiter {

  static final int DEFAULT_MAX_FAILURES = 10;
  static final long DEFAULT_WINDOW_MS = 10 * 60 * 1000L;
  /** 키가 이만큼 쌓이면 창이 지난 키를 한 번 쓸어낸다 (이메일을 바꿔 가며 두드려도 메모리가 안 불게). */
  private static final int SWEEP_THRESHOLD = 10_000;

  private final int maxFailures;
  private final long windowMs;
  private final LongSupplier clock;
  private final Map<String, Deque<Long>> failures = new ConcurrentHashMap<>();

  LoginAttemptLimiter() {
    this(DEFAULT_MAX_FAILURES, DEFAULT_WINDOW_MS, System::currentTimeMillis);
  }

  LoginAttemptLimiter(int maxFailures, long windowMs, LongSupplier clock) {
    this.maxFailures = maxFailures;
    this.windowMs = windowMs;
    this.clock = clock;
  }

  static String key(AccountRole role, String email) {
    return role + ":" + (email == null ? "" : email.trim().toLowerCase(Locale.ROOT));
  }

  boolean blocked(String key) {
    Deque<Long> q = failures.get(key);
    if (q == null) return false;
    synchronized (q) {
      prune(q, clock.getAsLong());
      return q.size() >= maxFailures;
    }
  }

  void recordFailure(String key) {
    long now = clock.getAsLong();
    if (failures.size() >= SWEEP_THRESHOLD) sweep(now);
    Deque<Long> q = failures.computeIfAbsent(key, k -> new ArrayDeque<>());
    synchronized (q) {
      prune(q, now);
      q.addLast(now);
    }
  }

  void reset(String key) {
    failures.remove(key);
  }

  private void prune(Deque<Long> q, long now) {
    while (!q.isEmpty() && now - q.peekFirst() >= windowMs) q.pollFirst();
  }

  private void sweep(long now) {
    failures
      .entrySet()
      .removeIf(e -> {
        Deque<Long> q = e.getValue();
        synchronized (q) {
          prune(q, now);
          return q.isEmpty();
        }
      });
  }
}
