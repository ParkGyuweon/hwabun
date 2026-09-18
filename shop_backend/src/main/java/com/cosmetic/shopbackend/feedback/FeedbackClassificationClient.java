package com.cosmetic.shopbackend.feedback;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/** Internal client for the recommendation server's LLM-backed feedback classifier. */
@Component
public class FeedbackClassificationClient {

  private final RestClient client;

  public FeedbackClassificationClient(
    @Value("${recommendation.url:http://localhost:8300}") String baseUrl,
    @Value("${recommendation.feedback-timeout-ms:30000}") int timeoutMs
  ) {
    var factory = new org.springframework.http.client.SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofMillis(timeoutMs));
    factory.setReadTimeout(Duration.ofMillis(timeoutMs));
    client = RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
  }

  public List<ClassificationResult> classify(List<FeedbackItem> items) {
    List<Map<String, Object>> payloadItems = new ArrayList<>();
    for (FeedbackItem item : items) {
      Map<String, Object> payload = new LinkedHashMap<>();
      payload.put("feedback_id", item.feedbackId());
      payload.put("product_id", item.productId());
      payload.put("axis_id", item.axisId());
      payload.put("body", item.body());
      payloadItems.add(payload);
    }

    try {
      Map<?, ?> response = client.post()
        .uri("/api/feedback/classify")
        .contentType(MediaType.APPLICATION_JSON)
        .body(Map.of("items", payloadItems))
        .retrieve()
        .body(Map.class);
      if (response == null || !(response.get("results") instanceof List<?> results)) {
        throw new FeedbackClassificationException("classifier response has no results");
      }
      return results.stream()
        .filter(Map.class::isInstance)
        .map(value -> ClassificationResult.from((Map<?, ?>) value))
        .toList();
    } catch (RestClientException exception) {
      throw new FeedbackClassificationException("recommendation classifier is unavailable", exception);
    }
  }

  public record FeedbackItem(
    String feedbackId,
    String productId,
    String axisId,
    String body
  ) {}

  public record ClassificationResult(
    String feedbackId,
    String status,
    List<Label> labels,
    String primaryAxisId,
    String primaryCategoryId,
    String offAxisHint,
    List<String> bannedTerms,
    boolean hiddenByDefault,
    String classifier,
    String vocabVersion,
    String classifiedAt
  ) {

    static ClassificationResult from(Map<?, ?> value) {
      return new ClassificationResult(
        text(value.get("feedback_id"), value.get("feedbackId")),
        text(value.get("status")),
        labels(value.get("labels")),
        text(value.get("primary_axis_id"), value.get("primaryAxisId"), primaryAxis(value)),
        text(value.get("primary_category_id"), value.get("primaryCategoryId"), primaryCategory(value)),
        text(value.get("off_axis_hint"), value.get("offAxisHint")),
        strings(value.get("banned_terms"), value.get("bannedTerms")),
        bool(value.get("hidden_by_default"), value.get("hiddenByDefault")),
        text(value.get("classifier")),
        text(value.get("vocab_version"), value.get("vocabVersion")),
        text(value.get("classified_at"), value.get("classifiedAt"))
      );
    }

    private static List<Label> labels(Object raw) {
      if (!(raw instanceof List<?> values)) return List.of();
      return values.stream()
        .filter(Map.class::isInstance)
        .map(value -> {
          Map<?, ?> label = (Map<?, ?>) value;
          return new Label(
            text(label.get("axis_id"), label.get("axisId")),
            text(label.get("category_id"), label.get("categoryId"))
          );
        })
        .filter(label -> label.axisId() != null && label.categoryId() != null)
        .toList();
    }

    private static List<String> strings(Object... values) {
      for (Object raw : values) {
        if (raw instanceof List<?> list) {
          return list.stream().map(String::valueOf).toList();
        }
      }
      return List.of();
    }

    private static boolean bool(Object... values) {
      for (Object value : values) {
        if (value instanceof Boolean bool) return bool;
        if (value instanceof Number number) return number.intValue() != 0;
      }
      return false;
    }

    private static String text(Object... values) {
      for (Object value : values) {
        if (value != null && !String.valueOf(value).isBlank()) return String.valueOf(value);
      }
      return null;
    }

    private static Object primaryAxis(Map<?, ?> value) {
      return value.get("primary") instanceof Map<?, ?> primary
        ? primary.get("axis_id") != null ? primary.get("axis_id") : primary.get("axisId")
        : null;
    }

    private static Object primaryCategory(Map<?, ?> value) {
      return value.get("primary") instanceof Map<?, ?> primary
        ? primary.get("category_id") != null ? primary.get("category_id") : primary.get("categoryId")
        : null;
    }
  }

  public record Label(String axisId, String categoryId) {}

  public static class FeedbackClassificationException extends RuntimeException {
    public FeedbackClassificationException(String message) {
      super(message);
    }

    public FeedbackClassificationException(String message, Throwable cause) {
      super(message, cause);
    }
  }
}
