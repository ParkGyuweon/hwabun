package com.cosmetic.shopbackend.payment;

import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * PortOne 결제 웹훅. 본문은 "이 paymentId 를 다시 확인해 달라"는 신호로만 쓴다 —
 * 상태·금액 등 본문 값은 절대 믿지 않고, PortOne API 를 다시 조회해 confirm 과 같은 검증을 통과할 때만
 * 주문을 PAID 로 바꾼다. 그래서 위조 요청이 와도 할 수 있는 일은 "조회 한 번 더" 뿐이다.
 *
 * <p>인증 없이 열려 있다(SecurityConfig permitAll). 받는 형식:
 * V2 웹훅 {@code {"type":"Transaction.Paid","data":{"paymentId":"..."}}} 와
 * 구버전 {@code {"payment_id":"..."}} 둘 다.
 */
@RestController
@RequestMapping("/api/payments/portone")
public class PortOneWebhookController {

  private static final Logger log = LoggerFactory.getLogger(PortOneWebhookController.class);
  private final PaymentConfirmationService confirmations;

  public PortOneWebhookController(PaymentConfirmationService confirmations) {
    this.confirmations = confirmations;
  }

  public record WebhookResult(String result) {}

  @PostMapping("/webhook")
  public WebhookResult webhook(@RequestBody(required = false) Map<String, Object> body) {
    String paymentId = paymentId(body);
    String orderId = PaymentConfirmationService.orderIdFromPaymentId(paymentId);
    if (orderId == null) {
      log.info("portone webhook ignored: no recognizable paymentId");
      return new WebhookResult("IGNORED");
    }
    // PortOne 조회 실패(타임아웃·5xx)는 예외 그대로 5xx 로 돌려 PortOne 이 재전송하게 둔다.
    PaymentConfirmationService.ReconcileResult result = confirmations.reconcile(orderId);
    log.info("portone webhook handled orderId={} result={}", orderId, result);
    return new WebhookResult(result.name());
  }

  static String paymentId(Map<String, Object> body) {
    if (body == null) return null;
    Object data = body.get("data");
    if (data instanceof Map<?, ?> map && map.get("paymentId") instanceof String id) return id;
    if (body.get("payment_id") instanceof String id) return id;
    return null;
  }
}
