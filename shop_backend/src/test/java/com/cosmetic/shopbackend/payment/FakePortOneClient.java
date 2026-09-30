package com.cosmetic.shopbackend.payment;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** 네트워크 없이 PortOne 조회 결과를 정해 두는 가짜. 등록 안 된 paymentId 는 실제 클라이언트처럼 409(원래 404). */
class FakePortOneClient extends PortOneClient {

  private final Map<String, Map<String, Object>> payments = new HashMap<>();
  private final Map<String, RuntimeException> failures = new HashMap<>();
  final List<String> lookups = new ArrayList<>();

  FakePortOneClient() {
    super("http://localhost:1", "", 1000);
  }

  FakePortOneClient paid(String orderId, long total) {
    return put(orderId, "PAID", total, orderId);
  }

  FakePortOneClient put(String orderId, String status, long total, String customOrderId) {
    String paymentId = PaymentConfirmationService.paymentIdFor(orderId);
    payments.put(
      paymentId,
      Map.of(
        "id", paymentId,
        "status", status,
        "currency", "KRW",
        "amount", Map.of("total", total),
        "customData", Map.of("orderId", customOrderId),
        "paidAt", "2026-09-29T01:00:00Z"
      )
    );
    return this;
  }

  FakePortOneClient failing(String orderId, RuntimeException exception) {
    failures.put(PaymentConfirmationService.paymentIdFor(orderId), exception);
    return this;
  }

  @Override
  public Map<String, Object> payment(String paymentId) {
    lookups.add(paymentId);
    RuntimeException failure = failures.get(paymentId);
    if (failure != null) throw failure;
    Map<String, Object> payment = payments.get(paymentId);
    if (payment == null) {
      throw new ResponseStatusException(HttpStatus.CONFLICT, "PortOne payment lookup failed");
    }
    return payment;
  }
}
