package com.cosmetic.shopbackend.commerce;

import java.math.BigDecimal;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.server.ResponseStatusException;

/**
 * Browser SDK의 완료 응답은 신뢰하지 않는다. 서버가 PortOne V2 API에서 다시
 * 결제 상태와 금액을 확인한 값만 주문 상태 변경에 사용한다.
 */
@Component
public class PortOnePaymentVerifier {

  private final RestClient client;
  private final String apiSecret;

  public PortOnePaymentVerifier(
    @Value("${PORTONE_API_SECRET:}") String apiSecret
  ) {
    this.client = RestClient.builder().baseUrl("https://api.portone.io").build();
    this.apiSecret = apiSecret;
  }

  public VerifiedPayment verify(String paymentId) {
    if (apiSecret == null || apiSecret.isBlank()) {
      throw new ResponseStatusException(
        HttpStatus.SERVICE_UNAVAILABLE,
        "PortOne payment verification is not configured"
      );
    }

    try {
      Map<?, ?> payment = client
        .get()
        .uri("/payments/{paymentId}", paymentId)
        .header(HttpHeaders.AUTHORIZATION, "PortOne " + apiSecret)
        .retrieve()
        .body(Map.class);
      if (payment == null) {
        throw invalidPayment();
      }

      Object amount = payment.get("amount");
      if (!(amount instanceof Map<?, ?> amountMap)) {
        throw invalidPayment();
      }
      Object total = amountMap.get("total");
      if (total == null) {
        throw invalidPayment();
      }
      return new VerifiedPayment(
        String.valueOf(payment.get("id")),
        String.valueOf(payment.get("status")),
        new BigDecimal(String.valueOf(total)),
        String.valueOf(payment.get("currency"))
      );
    } catch (ResponseStatusException exception) {
      throw exception;
    } catch (NumberFormatException | RestClientException exception) {
      throw new ResponseStatusException(
        HttpStatus.BAD_GATEWAY,
        "PortOne payment verification failed"
      );
    }
  }

  private ResponseStatusException invalidPayment() {
    return new ResponseStatusException(
      HttpStatus.UNPROCESSABLE_ENTITY,
      "invalid PortOne payment response"
    );
  }

  public record VerifiedPayment(
    String id,
    String status,
    BigDecimal totalAmount,
    String currency
  ) {}
}
