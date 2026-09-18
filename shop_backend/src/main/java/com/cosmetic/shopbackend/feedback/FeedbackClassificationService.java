package com.cosmetic.shopbackend.feedback;

import com.cosmetic.shopbackend.feedback.FeedbackClassificationClient.ClassificationResult;
import com.cosmetic.shopbackend.feedback.FeedbackClassificationClient.FeedbackItem;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Service
public class FeedbackClassificationService {

  private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
  private static final Logger log = LoggerFactory.getLogger(FeedbackClassificationService.class);
  private final JdbcTemplate jdbc;
  private final FeedbackClassificationClient classifier;
  private final TransactionTemplate transactions;
  private final tools.jackson.databind.ObjectMapper objectMapper;
  private final Executor executor;
  private final AtomicBoolean running = new AtomicBoolean(false);
  private final int batchSize;

  public FeedbackClassificationService(
    JdbcTemplate jdbc,
    FeedbackClassificationClient classifier,
    PlatformTransactionManager transactionManager,
    tools.jackson.databind.ObjectMapper objectMapper,
    @org.springframework.beans.factory.annotation.Qualifier("feedbackClassificationExecutor") Executor executor,
    @Value("${shop.feedback.classify.batch-size:200}") int batchSize
  ) {
    this.jdbc = jdbc;
    this.classifier = classifier;
    this.transactions = new TransactionTemplate(transactionManager);
    this.objectMapper = objectMapper;
    this.executor = executor;
    this.batchSize = batchSize;
  }

  /**
   * 분류 작업을 백그라운드에서 시작한다. 한 컨테이너에서 스케줄러와 수동 요청이
   * 같은 미분류 건을 동시에 추천 서버로 보내지 않도록 전체 실행을 하나로 직렬화한다.
   */
  public boolean startAsync(String brandId, Integer requestedLimit) {
    if (!running.compareAndSet(false, true)) return false;
    executor.execute(() -> {
      try {
        RunResult result = classifyPending(brandId, requestedLimit);
        log.info(
          "feedback classification async status={} selected={} completed={} failed={} brandId={}",
          result.status(), result.selected(), result.completed(), result.failed(), brandId
        );
      } catch (RuntimeException exception) {
        log.error("feedback classification async failed brandId={}", brandId, exception);
      } finally {
        running.set(false);
      }
    });
    return true;
  }

  public boolean isRunning() {
    return running.get();
  }

  public RunResult classifyPending(String brandId, Integer requestedLimit) {
    int limit = requestedLimit == null ? batchSize : Math.min(Math.max(requestedLimit, 1), batchSize);
    List<FeedbackRow> rows = selectPending(brandId, limit);
    if (rows.isEmpty()) return new RunResult(0, 0, 0, "EMPTY");

    List<ClassificationResult> results;
    try {
      results = classifier.classify(rows.stream().map(FeedbackRow::item).toList());
    } catch (FeedbackClassificationClient.FeedbackClassificationException exception) {
      return new RunResult(rows.size(), 0, 0, "SKIPPED");
    }

    Map<String, ClassificationResult> byFeedbackId = results.stream()
      .filter(result -> result.feedbackId() != null)
      .collect(java.util.stream.Collectors.toMap(
        ClassificationResult::feedbackId,
        result -> result,
        (first, ignored) -> first
      ));
    int completed = 0;
    int failed = 0;
    for (FeedbackRow row : rows) {
      ClassificationResult result = byFeedbackId.get(row.feedbackId());
      if (result == null) continue;
      persist(row, result);
      if ("COMPLETED".equalsIgnoreCase(result.status())) completed++;
      else if ("FAILED".equalsIgnoreCase(result.status())) failed++;
    }
    return new RunResult(rows.size(), completed, failed, "COMPLETED");
  }

  public int defaultBatchSize() {
    return batchSize;
  }

  private List<FeedbackRow> selectPending(String brandId, int limit) {
    String sql = "select f.feedback_id,f.product_id,f.axis_id,f.body " +
      "from feedback f " +
      "join feedback_classification fc on fc.feedback_id=f.feedback_id " +
      "join product p on p.product_id=f.product_id " +
      "where f.status <> 'DELETED' and fc.classification_status in ('PENDING','FAILED') " +
      (brandId == null ? "" : "and p.brand_id=? ") +
      "order by f.created_at,f.feedback_id limit ?";
    if (brandId == null) {
      return jdbc.query(sql, (rs, rowNum) -> row(rs, rowNum), limit);
    }
    return jdbc.query(sql, (rs, rowNum) -> row(rs, rowNum), brandId, limit);
  }

  private FeedbackRow row(java.sql.ResultSet rs, int rowNum) throws java.sql.SQLException {
    return new FeedbackRow(
      rs.getString("feedback_id"),
      rs.getString("product_id"),
      rs.getString("axis_id"),
      rs.getString("body")
    );
  }

  private void persist(FeedbackRow row, ClassificationResult result) {
    transactions.executeWithoutResult(status -> {
      jdbc.update("delete from feedback_classification_label where feedback_id=?", row.feedbackId());
      jdbc.update(
        "update feedback_classification set classifier=?,vocab_version=?,primary_axis_id=?,primary_category_id=?,off_axis_hint=?,classification_status=?,classified_at=?,banned_terms_json=?,hidden_by_default=? where feedback_id=?",
        result.classifier(),
        result.vocabVersion(),
        result.primaryAxisId() == null ? row.axisId() : result.primaryAxisId(),
        result.primaryCategoryId(),
        result.offAxisHint(),
        statusOf(result),
        classifiedAt(result.classifiedAt()),
        bannedTerms(result),
        result.hiddenByDefault(),
        row.feedbackId()
      );
      if ("COMPLETED".equalsIgnoreCase(result.status())) {
        for (FeedbackClassificationClient.Label label : result.labels()) {
          jdbc.update(
            "insert into feedback_classification_label(feedback_id,axis_id,category_id) values(?,?,?)",
            row.feedbackId(),
            label.axisId(),
            label.categoryId()
          );
        }
      }
    });
  }

  private String statusOf(ClassificationResult result) {
    return "FAILED".equalsIgnoreCase(result.status()) ? "FAILED" : "COMPLETED";
  }

  private LocalDateTime classifiedAt(String value) {
    if (value == null || value.isBlank()) return LocalDateTime.now(SEOUL);
    try {
      return OffsetDateTime.parse(value).atZoneSameInstant(SEOUL).toLocalDateTime();
    } catch (RuntimeException ignored) {
      try {
        return Instant.parse(value).atZone(SEOUL).toLocalDateTime();
      } catch (RuntimeException ignoredAgain) {
        return LocalDateTime.now(SEOUL);
      }
    }
  }

  private String bannedTerms(ClassificationResult result) {
    try {
      return objectMapper.writeValueAsString(result.bannedTerms());
    } catch (Exception ignored) {
      return "[]";
    }
  }

  private record FeedbackRow(String feedbackId, String productId, String axisId, String body) {
    FeedbackItem item() {
      return new FeedbackItem(feedbackId, productId, axisId, body);
    }
  }

  public record RunResult(int selected, int completed, int failed, String status) {}
}
