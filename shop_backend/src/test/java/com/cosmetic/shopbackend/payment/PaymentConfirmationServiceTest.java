package com.cosmetic.shopbackend.payment;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.cosmetic.shopbackend.commerce.ShopOrder;
import com.cosmetic.shopbackend.commerce.ShopOrderRepository;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.web.server.ResponseStatusException;

class PaymentConfirmationServiceTest {

  @Test
  void matchingPortOnePaymentMarksOwnedOrderPaid() {
    ShopOrderRepository orders = mock(ShopOrderRepository.class);
    PortOneClient portOne = mock(PortOneClient.class);
    PlatformTransactionManager transactionManager = transactionManager();
    org.springframework.jdbc.core.JdbcTemplate jdbc = mock(org.springframework.jdbc.core.JdbcTemplate.class);
    ShopOrder created = order("order-1", ShopOrder.Status.CREATED, null);
    ShopOrder paid = order("order-1", ShopOrder.Status.PAID, "hwabun-order-1");
    when(orders.findById("order-1"))
      .thenReturn(Optional.of(created), Optional.of(paid));
    when(portOne.payment("hwabun-order-1")).thenReturn(
      Map.of(
        "id", "hwabun-order-1",
        "status", "PAID",
        "currency", "KRW",
        "amount", Map.of("total", 31900),
        "customData", Map.of("orderId", "order-1"),
        "paidAt", "2026-09-16T01:00:00Z"
      )
    );
    when(orders.markVerifiedPaid(anyString(), anyString(), anyString(), any(), any()))
      .thenReturn(1);

    var result = new PaymentConfirmationService(orders, portOne, transactionManager, jdbc)
      .confirm("order-1", "member-1", "hwabun-order-1");

    assertEquals("PAID", result.status());
    assertEquals("hwabun-order-1", result.paymentId());
    verify(orders).markVerifiedPaid(
      eq("order-1"),
      eq("member-1"),
      eq("hwabun-order-1"),
      eq(new BigDecimal("31900")),
      any(LocalDateTime.class)
    );
  }

  @Test
  void amountMismatchNeverMarksOrderPaid() {
    ShopOrderRepository orders = mock(ShopOrderRepository.class);
    PortOneClient portOne = mock(PortOneClient.class);
    org.springframework.jdbc.core.JdbcTemplate jdbc = mock(org.springframework.jdbc.core.JdbcTemplate.class);
    ShopOrder created = order("order-1", ShopOrder.Status.CREATED, null);
    when(orders.findById("order-1")).thenReturn(Optional.of(created));
    when(portOne.payment("hwabun-order-1")).thenReturn(
      Map.of(
        "id", "hwabun-order-1",
        "status", "PAID",
        "currency", "KRW",
        "amount", Map.of("total", 1),
        "customData", Map.of("orderId", "order-1")
      )
    );

    ResponseStatusException error = assertThrows(
      ResponseStatusException.class,
      () -> new PaymentConfirmationService(orders, portOne, transactionManager(), jdbc)
        .confirm("order-1", "member-1", "hwabun-order-1")
    );

    assertEquals(HttpStatus.CONFLICT, error.getStatusCode());
    verify(orders, never()).markVerifiedPaid(anyString(), anyString(), anyString(), any(), any());
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
    when(order.getPaymentProvider()).thenReturn(paymentId == null ? null : "PORTONE_TEST");
    when(order.getPaidAt()).thenReturn(LocalDateTime.of(2026, 9, 16, 10, 0));
    return order;
  }

  private PlatformTransactionManager transactionManager() {
    PlatformTransactionManager manager = mock(PlatformTransactionManager.class);
    when(manager.getTransaction(any())).thenReturn(mock(TransactionStatus.class));
    return manager;
  }
}
