package com.cosmetic.shopbackend.payment;

import java.time.Duration;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

@Component
public class PortOneClient {

  private final RestClient client;
  private final String apiSecret;

  public PortOneClient(
    @Value("${portone.api-url:https://api.portone.io}") String apiUrl,
    @Value("${PORTONE_API_SECRET:}") String apiSecret,
    @Value("${portone.timeout-ms:10000}") int timeoutMs
  ) {
    SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofMillis(Math.min(timeoutMs, 3000)));
    factory.setReadTimeout(Duration.ofMillis(timeoutMs));
    this.client = RestClient.builder().baseUrl(apiUrl).requestFactory(factory).build();
    this.apiSecret = apiSecret;
  }

  @SuppressWarnings("unchecked")
  public Map<String, Object> payment(String paymentId) {
    if (apiSecret.isBlank()) {
      throw new ResponseStatusException(
        HttpStatus.SERVICE_UNAVAILABLE,
        "PORTONE_API_SECRET is not configured"
      );
    }
    try {
      Map<String, Object> body = client
        .get()
        .uri("/payments/{paymentId}", paymentId)
        .header("Authorization", "PortOne " + apiSecret)
        .retrieve()
        .body(Map.class);
      if (body == null) throw new ResponseStatusException(
        HttpStatus.BAD_GATEWAY,
        "PortOne returned an empty response"
      );
      return body;
    } catch (RestClientResponseException exception) {
      HttpStatus mapped = exception.getStatusCode().value() == 404
        ? HttpStatus.CONFLICT
        : HttpStatus.BAD_GATEWAY;
      throw new ResponseStatusException(mapped, "PortOne payment lookup failed", exception);
    } catch (ResourceAccessException exception) {
      throw new ResponseStatusException(
        HttpStatus.SERVICE_UNAVAILABLE,
        "PortOne payment lookup timed out",
        exception
      );
    }
  }
}
