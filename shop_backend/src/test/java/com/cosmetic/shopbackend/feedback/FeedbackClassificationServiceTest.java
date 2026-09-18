package com.cosmetic.shopbackend.feedback;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.mock;

import java.util.concurrent.RejectedExecutionException;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

class FeedbackClassificationServiceTest {

  @Test
  void clearsRunningFlagWhenExecutorRejectsSubmission() {
    FeedbackClassificationService service = new FeedbackClassificationService(
      mock(JdbcTemplate.class),
      mock(FeedbackClassificationClient.class),
      mock(PlatformTransactionManager.class),
      mock(tools.jackson.databind.ObjectMapper.class),
      command -> {
        throw new RejectedExecutionException("executor is shutting down");
      },
      200
    );

    assertFalse(service.startAsync("brand-1", null));
    assertFalse(service.isRunning());
  }
}
