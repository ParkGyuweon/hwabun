package com.cosmetic.shopbackend.recommendation;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.server.ResponseStatusException;

/** Boundary for the internal, unauthenticated Python recommendation service. */
@Component
public class RecommendationClient {

  private final RestClient client;

  public RecommendationClient(
    @Value("${recommendation.url:http://localhost:8300}") String baseUrl,
    @Value("${recommendation.timeout-ms:300}") int timeoutMs
  ) {
    SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofMillis(timeoutMs));
    factory.setReadTimeout(Duration.ofMillis(timeoutMs));
    client = RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
  }

  public ResponseEntity<String> recommend(String accountId, RecommendationQuery query) {
    try {
      return client.get().uri(uri -> uri
        .path("/api/recommend")
        .queryParamIfPresent("persona_id", java.util.Optional.ofNullable(accountId))
        .queryParam("size", query.size())
        .queryParam("reserved", query.reserved())
        .queryParam("banner_slots", query.bannerSlots())
        .queryParam("axes", query.axes())
        .queryParam("hero", query.hero())
        .queryParamIfPresent("skin_type", java.util.Optional.ofNullable(query.skinType()))
        .queryParamIfPresent("skin_tone", java.util.Optional.ofNullable(query.skinTone()))
        .queryParamIfPresent("hair_color", java.util.Optional.ofNullable(query.hairColor()))
        .queryParamIfPresent("eye_color", java.util.Optional.ofNullable(query.eyeColor()))
        .build())
        .exchange((request, response) -> {
          HttpStatusCode status = response.getStatusCode();
          MediaType contentType = response.getHeaders().getContentType();
          return ResponseEntity.status(status)
            .contentType(contentType == null ? MediaType.APPLICATION_JSON : contentType)
            .body(response.bodyTo(String.class));
        });
    } catch (ResourceAccessException exception) {
      throw unavailable(exception);
    } catch (RestClientException exception) {
      throw unavailable(exception);
    }
  }

  private ResponseStatusException unavailable(Exception exception) {
    return new ResponseStatusException(
      HttpStatus.SERVICE_UNAVAILABLE,
      "recommendation service is unavailable",
      exception
    );
  }
}
