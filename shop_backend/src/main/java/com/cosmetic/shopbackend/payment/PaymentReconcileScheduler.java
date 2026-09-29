package com.cosmetic.shopbackend.payment;

import com.cosmetic.shopbackend.commerce.ShopOrderRepository;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * "결제는 됐는데 서버 확인(confirm)이 실패하면?" 에 대한 안전망.
 * 브라우저가 결제 후 /confirm 을 못 부르고 끊겨도, 몇 분마다 CREATED 주문을 PortOne 에 다시 물어
 * 결제 완료·검증 통과면 PAID 로 맞춘다. 판단은 항상 PortOne 조회 결과로만 한다.
 */
@Component
public class PaymentReconcileScheduler {

  private static final Logger log = LoggerFactory.getLogger(PaymentReconcileScheduler.class);
  private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

  private final PaymentConfirmationService confirmations;
  private final ShopOrderRepository orders;
  private final boolean enabled;
  private final boolean portOneConfigured;
  private final Duration minAge;
  private final Duration maxAge;
  private final int batchSize;
  private final Clock clock;
  private final AtomicBoolean running = new AtomicBoolean(false);
  private final AtomicBoolean disabledLogged = new AtomicBoolean(false);

  @Autowired
  public PaymentReconcileScheduler(
    PaymentConfirmationService confirmations,
    ShopOrderRepository orders,
    @Value("${shop.payment.reconcile.enabled:true}") boolean enabled,
    @Value("${PORTONE_API_SECRET:}") String portOneSecret,
    @Value("${shop.payment.reconcile.min-age-seconds:120}") long minAgeSeconds,
    @Value("${shop.payment.reconcile.max-age-hours:24}") long maxAgeHours,
    @Value("${shop.payment.reconcile.batch-size:50}") int batchSize
  ) {
    this(
      confirmations,
      orders,
      enabled,
      portOneSecret != null && !portOneSecret.isBlank(),
      Duration.ofSeconds(minAgeSeconds),
      Duration.ofHours(maxAgeHours),
      batchSize,
      Clock.system(SEOUL)
    );
  }

  PaymentReconcileScheduler(
    PaymentConfirmationService confirmations,
    ShopOrderRepository orders,
    boolean enabled,
    boolean portOneConfigured,
    Duration minAge,
    Duration maxAge,
    int batchSize,
    Clock clock
  ) {
    this.confirmations = confirmations;
    this.orders = orders;
    this.enabled = enabled;
    this.portOneConfigured = portOneConfigured;
    this.minAge = minAge;
    this.maxAge = maxAge;
    this.batchSize = Math.max(1, batchSize);
    this.clock = clock;
  }

  public boolean isActive() {
    return enabled && portOneConfigured;
  }

  @Scheduled(
    fixedDelayString = "${shop.payment.reconcile.interval-ms:300000}",
    initialDelayString = "${shop.payment.reconcile.initial-delay-ms:60000}"
  )
  public void scheduledRun() {
    reconcilePending();
  }

  /** 한 회차를 돌리고 결과별 건수를 돌려준다. 꺼져 있거나 이미 도는 중이면 빈 결과. */
  public Map<PaymentConfirmationService.ReconcileResult, Integer> reconcilePending() {
    Map<PaymentConfirmationService.ReconcileResult, Integer> counts = new EnumMap<>(
      PaymentConfirmationService.ReconcileResult.class
    );
    if (!isActive()) {
      if (disabledLogged.compareAndSet(false, true)) {
        log.info(
          "payment reconcile disabled (enabled={}, portOneConfigured={})",
          enabled,
          portOneConfigured
        );
      }
      return counts;
    }
    if (!running.compareAndSet(false, true)) {
      log.info("payment reconcile skipped because another run is in progress");
      return counts;
    }
    int failures = 0;
    try {
      LocalDateTime now = LocalDateTime.now(clock);
      List<String> candidates = orders.findReconcileCandidateIds(
        now.minus(maxAge),
        now.minus(minAge),
        batchSize
      );
      for (String orderId : candidates) {
        try {
          counts.merge(confirmations.reconcile(orderId), 1, Integer::sum);
        } catch (RuntimeException exception) {
          failures++;
          log.warn("payment reconcile lookup failed orderId={} error={}", orderId, exception.toString());
        }
      }
      int recovered = counts.getOrDefault(PaymentConfirmationService.ReconcileResult.RECOVERED, 0);
      int mismatched = counts.getOrDefault(PaymentConfirmationService.ReconcileResult.MISMATCH, 0);
      if (recovered > 0 || mismatched > 0 || failures > 0) {
        log.warn(
          "payment reconcile finished candidates={} results={} failures={}",
          candidates.size(),
          counts,
          failures
        );
      } else {
        log.info("payment reconcile finished candidates={} results={}", candidates.size(), counts);
      }
      return counts;
    } finally {
      running.set(false);
    }
  }
}
