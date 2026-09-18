package com.cosmetic.shopbackend.feedback;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class FeedbackClassificationScheduler {

  private static final Logger log = LoggerFactory.getLogger(FeedbackClassificationScheduler.class);
  private final FeedbackClassificationService classifications;

  public FeedbackClassificationScheduler(FeedbackClassificationService classifications) {
    this.classifications = classifications;
  }

  @Scheduled(
    cron = "${shop.feedback.classify.cron:0 0 6 * * *}",
    zone = "Asia/Seoul"
  )
  public void classifyDaily() {
    FeedbackClassificationService.RunResult result = classifications.classifyPending(null, null);
    log.info(
      "feedback classification batch status={} selected={} completed={} failed={}",
      result.status(), result.selected(), result.completed(), result.failed()
    );
  }
}
