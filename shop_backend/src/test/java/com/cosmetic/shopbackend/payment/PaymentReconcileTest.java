package com.cosmetic.shopbackend.payment;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.cosmetic.shopbackend.commerce.ShopOrder;
import com.cosmetic.shopbackend.commerce.ShopOrderRepository;
import com.cosmetic.shopbackend.payment.PaymentConfirmationService.ReconcileResult;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.web.server.ResponseStatusException;

class PaymentReconcileTest {

  private final ShopOrderRepository orders = mock(ShopOrderRepository.class);
  private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
  private final FakePortOneClient portOne = new FakePortOneClient();

  private PaymentConfirmationService service() {
    PlatformTransactionManager manager = mock(PlatformTransactionManager.class);
    when(manager.getTransaction(any())).thenReturn(mock(TransactionStatus.class));
    return new PaymentConfirmationService(orders, portOne, manager, jdbc);
  }

  @Test
  void paidAndVerifiedPaymentRecoversCreatedOrder() {
    stubRecoverable("order-1");
    when(orders.markVerifiedPaid(anyString(), anyString(), anyString(), any(), any())).thenReturn(1);
    portOne.paid("order-1", 31900);

    assertEquals(ReconcileResult.RECOVERED, service().reconcile("order-1"));
    verify(orders).markVerifiedPaid(
      eq("order-1"),
      eq("member-1"),
      eq("hwabun-order-1"),
      eq(new BigDecimal("31900")),
      any(LocalDateTime.class)
    );
  }

  @Test
  void amountMismatchIsReportedAndNeverMarksPaid() {
    stubFind("order-1", ShopOrder.Status.CREATED, null);
    portOne.paid("order-1", 1);

    assertEquals(ReconcileResult.MISMATCH, service().reconcile("order-1"));
    verify(orders, never()).markVerifiedPaid(anyString(), anyString(), anyString(), any(), any());
  }

  @Test
  void customDataForAnotherOrderIsMismatch() {
    stubFind("order-1", ShopOrder.Status.CREATED, null);
    portOne.put("order-1", "PAID", 31900, "order-2");

    assertEquals(ReconcileResult.MISMATCH, service().reconcile("order-1"));
    verify(orders, never()).markVerifiedPaid(anyString(), anyString(), anyString(), any(), any());
  }

  @Test
  void notPaidOrMissingPaymentLeavesOrderCreated() {
    stubFind("order-1", ShopOrder.Status.CREATED, null);
    stubFind("order-2", ShopOrder.Status.CREATED, null);
    portOne.put("order-1", "READY", 31900, "order-1");

    assertEquals(ReconcileResult.NOT_PAID, service().reconcile("order-1"));
    assertEquals(ReconcileResult.NO_PAYMENT, service().reconcile("order-2"));
    verify(orders, never()).markVerifiedPaid(anyString(), anyString(), anyString(), any(), any());
  }

  @Test
  void alreadyPaidOrderIsNotLookedUpAgain() {
    stubFind("order-1", ShopOrder.Status.PAID, "hwabun-order-1");

    assertEquals(ReconcileResult.ALREADY_PAID, service().reconcile("order-1"));
    assertTrue(portOne.lookups.isEmpty());
  }

  @Test
  void portOneOutagePropagatesSoCallerRetriesLater() {
    stubFind("order-1", ShopOrder.Status.CREATED, null);
    portOne.failing("order-1", new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "timeout"));

    assertThrows(ResponseStatusException.class, () -> service().reconcile("order-1"));
  }

  @Test
  void schedulerReconcilesCandidatesInWindowAndSurvivesFailures() {
    Instant now = Instant.parse("2026-09-29T03:00:00Z");
    Clock clock = Clock.fixed(now, ZoneId.of("Asia/Seoul"));
    LocalDateTime local = LocalDateTime.ofInstant(now, ZoneId.of("Asia/Seoul"));
    when(orders.findReconcileCandidateIds(local.minusHours(24), local.minusMinutes(2), 50))
      .thenReturn(List.of("order-1", "order-2", "order-3"));
    stubRecoverable("order-1");
    stubFind("order-2", ShopOrder.Status.CREATED, null);
    stubFind("order-3", ShopOrder.Status.CREATED, null);
    when(orders.markVerifiedPaid(anyString(), anyString(), anyString(), any(), any())).thenReturn(1);
    portOne
      .paid("order-1", 31900)
      .failing("order-2", new ResponseStatusException(HttpStatus.BAD_GATEWAY, "down"));

    Map<ReconcileResult, Integer> counts = scheduler(true, true, clock).reconcilePending();

    assertEquals(1, counts.get(ReconcileResult.RECOVERED));
    assertEquals(1, counts.get(ReconcileResult.NO_PAYMENT));
    assertEquals(List.of("hwabun-order-1", "hwabun-order-2", "hwabun-order-3"), portOne.lookups);
  }

  @Test
  void schedulerDoesNothingWhenDisabledOrSecretMissing() {
    Clock clock = Clock.systemUTC();
    assertTrue(scheduler(false, true, clock).reconcilePending().isEmpty());
    assertTrue(scheduler(true, false, clock).reconcilePending().isEmpty());
    verify(orders, never()).findReconcileCandidateIds(any(), any(), anyInt());
    assertTrue(portOne.lookups.isEmpty());
  }

  @Test
  void webhookReQueriesPortOneAndIgnoresBodyStatus() {
    stubFind("order-1", ShopOrder.Status.CREATED, null);
    // 본문은 Paid 라고 주장하지만 PortOne 에는 결제가 없다 → PAID 로 바꾸지 않는다.
    var controller = new PortOneWebhookController(service());
    var result = controller.webhook(
      Map.of("type", "Transaction.Paid", "data", Map.of("paymentId", "hwabun-order-1", "status", "PAID"))
    );

    assertEquals("NO_PAYMENT", result.result());
    assertEquals(List.of("hwabun-order-1"), portOne.lookups);
    verify(orders, never()).markVerifiedPaid(anyString(), anyString(), anyString(), any(), any());
  }

  @Test
  void webhookRecoversPaidOrderAndAcceptsLegacyBody() {
    stubRecoverable("order-1");
    when(orders.markVerifiedPaid(anyString(), anyString(), anyString(), any(), any())).thenReturn(1);
    portOne.paid("order-1", 31900);

    var result = new PortOneWebhookController(service()).webhook(Map.of("payment_id", "hwabun-order-1"));

    assertEquals("RECOVERED", result.result());
  }

  @Test
  void webhookIgnoresForeignOrMissingPaymentIds() {
    var controller = new PortOneWebhookController(service());

    assertEquals("IGNORED", controller.webhook(Map.of("data", Map.of("paymentId", "other-123"))).result());
    assertEquals("IGNORED", controller.webhook(Map.of("type", "Transaction.Paid")).result());
    assertEquals("IGNORED", controller.webhook(null).result());
    assertTrue(portOne.lookups.isEmpty());
  }

  private PaymentReconcileScheduler scheduler(boolean enabled, boolean configured, Clock clock) {
    return new PaymentReconcileScheduler(
      service(),
      orders,
      enabled,
      configured,
      Duration.ofMinutes(2),
      Duration.ofHours(24),
      50,
      clock
    );
  }

  private void stubFind(String id, ShopOrder.Status status, String paymentId) {
    ShopOrder order = order(id, status, paymentId);
    when(orders.findById(id)).thenReturn(Optional.of(order));
  }

  private void stubRecoverable(String id) {
    ShopOrder created = order(id, ShopOrder.Status.CREATED, null);
    ShopOrder paid = order(id, ShopOrder.Status.PAID, PaymentConfirmationService.paymentIdFor(id));
    when(orders.findById(id)).thenReturn(Optional.of(created), Optional.of(paid));
  }

  private ShopOrder order(String id, ShopOrder.Status status, String paymentId) {
    ShopOrder order = mock(ShopOrder.class);
    when(order.getId()).thenReturn(id);
    when(order.getMemberId()).thenReturn("member-1");
    when(order.getStatus()).thenReturn(status);
    when(order.getTotalAmount()).thenReturn(new BigDecimal("31900"));
    when(order.getPaidAmount()).thenReturn(new BigDecimal("31900"));
    when(order.getCurrency()).thenReturn("KRW");
    when(order.getPaymentId()).thenReturn(paymentId);
    when(order.getPaidAt()).thenReturn(LocalDateTime.of(2026, 9, 29, 10, 0));
    return order;
  }
}
