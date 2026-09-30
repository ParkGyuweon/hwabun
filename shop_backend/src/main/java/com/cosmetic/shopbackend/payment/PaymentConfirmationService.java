package com.cosmetic.shopbackend.payment;

import com.cosmetic.shopbackend.commerce.ShopOrder;
import com.cosmetic.shopbackend.commerce.ShopOrderRepository;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.Map;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PaymentConfirmationService {

  private static final Logger log = LoggerFactory.getLogger(PaymentConfirmationService.class);
  private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
  /** 프론트(frontend/src/lib/payment.ts paymentIdFor)와 같은 규칙이다. 주문 하나에 결제 id 하나. */
  static final String PAYMENT_ID_PREFIX = "hwabun-";
  private final ShopOrderRepository orders;
  private final PortOneClient portOne;
  private final TransactionTemplate transactions;
  private final JdbcTemplate jdbc;
  private final ObjectMapper objectMapper = new ObjectMapper();

  public PaymentConfirmationService(
    ShopOrderRepository orders,
    PortOneClient portOne,
    PlatformTransactionManager transactionManager,
    JdbcTemplate jdbc
  ) {
    this.orders = orders;
    this.portOne = portOne;
    this.transactions = new TransactionTemplate(transactionManager);
    this.jdbc = jdbc;
  }

  public Confirmation confirm(String orderId, String memberId, String paymentId) {
    ShopOrder order = ownedOrder(orderId, memberId);
    String expectedPaymentId = paymentIdFor(orderId);
    if (!expectedPaymentId.equals(paymentId)) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "paymentId does not match order");
    }
    if (order.getStatus() == ShopOrder.Status.PAID) {
      if (paymentId.equals(order.getPaymentId())) return view(order);
      throw new ResponseStatusException(HttpStatus.CONFLICT, "order was paid by another payment method");
    }
    if (order.getStatus() != ShopOrder.Status.CREATED) {
      throw new ResponseStatusException(HttpStatus.CONFLICT, "order cannot be paid in its current status");
    }

    Map<String, Object> payment = portOne.payment(paymentId);
    validate(payment, order, paymentId);
    LocalDateTime paidAt = paidAt(payment.get("paidAt"));
    return transactions.execute(status ->
      complete(orderId, memberId, paymentId, order.getTotalAmount(), paidAt)
    );
  }

  public static String paymentIdFor(String orderId) {
    return PAYMENT_ID_PREFIX + orderId;
  }

  /** paymentId 가 우리 규칙(hwabun-주문번호)이면 주문번호를, 아니면 null 을 준다. */
  public static String orderIdFromPaymentId(String paymentId) {
    if (paymentId == null || !paymentId.startsWith(PAYMENT_ID_PREFIX)) return null;
    String orderId = paymentId.substring(PAYMENT_ID_PREFIX.length());
    return orderId.isBlank() || orderId.length() > 64 ? null : orderId;
  }

  /**
   * 브라우저의 confirm 호출이 실패·누락된 주문을 서버가 스스로 맞춘다(스케줄러·웹훅 공용).
   * 회원 소유 검사 대신 PortOne 을 다시 조회해 confirm 과 같은 검증(상태·통화·금액·customData.orderId)을
   * 통과할 때만 CREATED→PAID 로 바꾼다. 조건부 update 라 confirm 과 동시에 돌아도 한 번만 반영된다.
   * PortOne 조회 자체가 실패(타임아웃·5xx)하면 예외를 그대로 던진다 — 다음 회차에 다시 시도한다.
   */
  public ReconcileResult reconcile(String orderId) {
    ShopOrder order = orders.findById(orderId).orElse(null);
    if (order == null) return ReconcileResult.ORDER_NOT_FOUND;
    if (order.getStatus() == ShopOrder.Status.PAID) return ReconcileResult.ALREADY_PAID;
    if (order.getStatus() != ShopOrder.Status.CREATED) return ReconcileResult.NOT_PAYABLE;

    String paymentId = paymentIdFor(orderId);
    Map<String, Object> payment;
    try {
      payment = portOne.payment(paymentId);
    } catch (ResponseStatusException exception) {
      // PortOneClient 는 PortOne 404 를 409 로 바꾼다 — 결제창을 열지 않았거나 결제가 안 만들어진 주문.
      if (exception.getStatusCode().value() == HttpStatus.CONFLICT.value()) {
        return ReconcileResult.NO_PAYMENT;
      }
      throw exception;
    }
    if (!"PAID".equals(String.valueOf(payment.get("status")))) return ReconcileResult.NOT_PAID;
    try {
      validate(payment, order, paymentId);
    } catch (ResponseStatusException exception) {
      log.warn(
        "payment reconcile mismatch orderId={} paymentId={} reason={}",
        orderId,
        paymentId,
        exception.getReason()
      );
      return ReconcileResult.MISMATCH;
    }
    LocalDateTime paidAt = paidAt(payment.get("paidAt"));
    String memberId = order.getMemberId();
    try {
      transactions.execute(status ->
        complete(orderId, memberId, paymentId, order.getTotalAmount(), paidAt)
      );
    } catch (ResponseStatusException exception) {
      if (exception.getStatusCode().value() == HttpStatus.CONFLICT.value()) {
        return ReconcileResult.NOT_PAYABLE;
      }
      throw exception;
    }
    log.info("payment reconciled orderId={} paymentId={}", orderId, paymentId);
    return ReconcileResult.RECOVERED;
  }

  public enum ReconcileResult {
    /** PortOne 에 결제 완료가 있어 이번에 PAID 로 바꿨다. */
    RECOVERED,
    ALREADY_PAID,
    /** PortOne 에 이 주문 결제가 없다(결제창 미진입 등). */
    NO_PAYMENT,
    /** PortOne 결제가 아직 PAID 가 아니다(READY·FAILED·CANCELLED 등). */
    NOT_PAID,
    /** PortOne 은 PAID 인데 금액·통화·주문번호가 안 맞는다 — 사람이 봐야 한다(환불 후보). */
    MISMATCH,
    NOT_PAYABLE,
    ORDER_NOT_FOUND,
  }

  private Confirmation complete(
    String orderId,
    String memberId,
    String paymentId,
    BigDecimal amount,
    LocalDateTime paidAt
  ) {
    int updated = orders.markVerifiedPaid(orderId, memberId, paymentId, amount, paidAt);
    jdbc.update(
      "insert into payment(payment_id,order_id,provider,status,amount,currency,paid_at,verified_at,raw_status) values(?,?,?,?,?,?,?,?,?) on duplicate key update status=values(status),amount=values(amount),paid_at=values(paid_at),verified_at=values(verified_at),raw_status=values(raw_status)",
      paymentId,
      orderId,
      "PORTONE_TEST",
      "PAID",
      amount,
      "KRW",
      paidAt,
      LocalDateTime.now(SEOUL),
      "PAID"
    );
    ShopOrder current = ownedOrder(orderId, memberId);
    if (updated == 0 && !paymentId.equals(current.getPaymentId())) {
      throw new ResponseStatusException(HttpStatus.CONFLICT, "order payment changed concurrently");
    }
    return view(current);
  }

  private ShopOrder ownedOrder(String orderId, String memberId) {
    return orders
      .findById(orderId)
      .filter(order -> order.getMemberId().equals(memberId))
      .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "order not found"));
  }

  @SuppressWarnings("unchecked")
  private void validate(Map<String, Object> payment, ShopOrder order, String paymentId) {
    if (!paymentId.equals(String.valueOf(payment.get("id")))) mismatch("payment id");
    if (!"PAID".equals(String.valueOf(payment.get("status")))) {
      throw new ResponseStatusException(HttpStatus.CONFLICT, "PortOne payment is not paid");
    }
    if (!order.getCurrency().equals(String.valueOf(payment.get("currency")))) mismatch("currency");
    Object amountValue = payment.get("amount");
    if (!(amountValue instanceof Map<?, ?>)) mismatch("amount");
    Map<String, Object> amount = (Map<String, Object>) amountValue;
    BigDecimal paid = decimal(amount.get("total"));
    if (paid.compareTo(order.getTotalAmount()) != 0) mismatch("amount");
    Object customDataValue = payment.get("customData");
    Map<?, ?> customData;
    if (customDataValue instanceof Map<?, ?> map) {
      customData = map;
    } else if (customDataValue instanceof String json) {
      try {
        customData = objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {});
      } catch (Exception exception) {
        mismatch("customData");
        return;
      }
    } else {
      mismatch("customData");
      return;
    }
    if (!order.getId().equals(String.valueOf(customData.get("orderId")))) mismatch("customData.orderId");
  }

  private BigDecimal decimal(Object value) {
    try {
      return new BigDecimal(String.valueOf(value));
    } catch (RuntimeException exception) {
      mismatch("amount");
      throw exception;
    }
  }

  private LocalDateTime paidAt(Object value) {
    if (value == null) return LocalDateTime.now(SEOUL);
    try {
      return OffsetDateTime.parse(String.valueOf(value)).atZoneSameInstant(SEOUL).toLocalDateTime();
    } catch (RuntimeException ignored) {
      try {
        return Instant.parse(String.valueOf(value)).atZone(SEOUL).toLocalDateTime();
      } catch (RuntimeException exception) {
        throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "PortOne paidAt is invalid", exception);
      }
    }
  }

  private void mismatch(String field) {
    throw new ResponseStatusException(HttpStatus.CONFLICT, "PortOne payment " + field + " mismatch");
  }

  private Confirmation view(ShopOrder order) {
    return new Confirmation(
      order.getId(),
      order.getStatus().name(),
      order.getPaymentId(),
      order.getPaidAmount(),
      order.getCurrency(),
      order.getPaidAt()
    );
  }

  public record Confirmation(
    String orderId,
    String status,
    String paymentId,
    BigDecimal paidAmount,
    String currency,
    LocalDateTime paidAt
  ) {}
}
