package com.cosmetic.shopbackend.dashboard;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.server.ResponseStatusException;

/**
 * 마트 조회 SQL 검증. 계약(`contracts/dashboard-mart-api-spec.md`)과 `dw-schema.md` §4 의 분모 정의가 기준이다.
 *
 * 검증의 중심은 둘이다.
 *   1. **반복되는 컬럼을 축으로 합산하지 않는가** — 상품 단위 값이 콘텐츠 종류마다 반복되는 마트가 여럿이다.
 *   2. **마트 하나가 없을 때 그 블록만 비는가** — 엔드포인트 전체가 죽으면 있는 마트까지 화면이 모의로 돌린다.
 */
class DashboardMartServiceTest {

  private static final String BRAND = "6018";
  private static final String SELLER = "seller-1";
  private static final String FROM = "2026-09-10";
  private static final String TO = "2026-09-11";

  private JdbcTemplate dw;
  private DashboardMartService service;

  @BeforeEach
  void setUp() {
    dw = DwTestSchema.freshDatabase();
    dw.update("insert into brand (brand_id, seller_account_id) values (?,?)", BRAND, SELLER);
    service = new DashboardMartService(dw, provider(dw));
  }

  @Test
  @DisplayName("가격 위치 API는 카테고리 중앙값을 쓰고 표본 3개 미만이면 전체 중앙값을 쓴다")
  void pricePositionUsesCatalogMedianAndFallback() {
    dw.execute("create table product (product_id varchar(64),brand_id varchar(64),product_name varchar(100),secondary_category varchar(64),status varchar(16))");
    dw.execute("create table product_variant (product_id varchar(64),price_krw decimal(18,2),status varchar(16))");
    dw.update("insert into product values ('P1',?,'mine','Serums','ACTIVE')", BRAND);
    dw.update("insert into product values ('P2','other','other-1','Serums','ACTIVE')");
    dw.update("insert into product values ('P3','other','other-2','Serums','ACTIVE')");
    dw.update("insert into product values ('P4',?,'mine-2','Masks','ACTIVE')", BRAND);
    dw.update("insert into product_variant values ('P1',20000,'ACTIVE')");
    dw.update("insert into product_variant values ('P2',10000,'ACTIVE')");
    dw.update("insert into product_variant values ('P3',30000,'ACTIVE')");
    dw.update("insert into product_variant values ('P4',50000,'ACTIVE')");

    List<?> products = (List<?>) service.pricePosition(SELLER, BRAND).get("products");
    Map<?, ?> first = (Map<?, ?>) products.get(0);
    Map<?, ?> second = (Map<?, ?>) products.get(1);
    assertEquals(2, products.size());
    assertEquals("category", first.get("reference_source"));
    assertEquals(20000D, decimal(first.get("reference_median_krw")));
    assertEquals(0D, decimal(first.get("price_difference_pct")));
    assertEquals("global_fallback", second.get("reference_source"));
    assertEquals(25000D, decimal(second.get("reference_median_krw")));
    assertEquals(100D, decimal(second.get("price_difference_pct")));
    assertThrows(ResponseStatusException.class, () -> service.pricePosition("other-seller", BRAND));
  }

  @Test
  @DisplayName("교차 브랜드 유입은 목적 브랜드·기간으로 읽고 실행축을 합산한 뒤 비율을 다시 계산한다")
  void crossBrandInflowAggregatesExecutionAxesAndFilters() {
    dw.execute("create table dw.cross_brand_daily (" +
      "destination_brand_id varchar(64) not null,event_date_kst date not null," +
      "actor_type varchar(32) not null,source varchar(32) not null,generator_type varchar(64)," +
      "scenario_id varchar(64),simulation_run_id varchar(64)," +
      "brand_view_sessions bigint not null,cross_brand_entry_sessions bigint not null," +
      "recommendation_cross_brand_entry_sessions bigint not null,banner_cross_brand_entry_sessions bigint not null," +
      "mart_processed_at timestamp(3) not null)");
    dw.update("insert into dw.cross_brand_daily values ('6018','2026-09-10','synthetic','simulator','agent_llm','s1','r1',50,10,6,2,'2026-09-11 02:00:00')");
    dw.update("insert into dw.cross_brand_daily values ('6018','2026-09-10','synthetic','simulator','python_batch','s2','r2',100,20,8,4,'2026-09-11 02:00:00')");
    dw.update("insert into dw.cross_brand_daily values ('6018','2026-09-10','web','web',null,null,null,50,10,1,1,'2026-09-11 02:00:00')");
    dw.update("insert into dw.cross_brand_daily values ('other','2026-09-10','synthetic','simulator','python_batch','s2','r2',900,200,80,40,'2026-09-11 02:00:00')");

    Map<String, Object> response = service.crossBrandInflow(SELLER, BRAND, FROM, TO, "all", "all");
    Map<?, ?> summary = (Map<?, ?>) response.get("summary");
    Map<?, ?> day = (Map<?, ?>) ((List<?>) response.get("daily")).getFirst();
    assertEquals("full", coverage(response));
    assertEquals(200L, number(summary.get("brand_view_sessions")));
    assertEquals(40L, number(summary.get("cross_brand_entry_sessions")));
    assertEquals(15L, number(summary.get("recommendation_cross_brand_entry_sessions")));
    assertEquals(7L, number(summary.get("banner_cross_brand_entry_sessions")));
    assertEquals(0.2D, decimal(summary.get("cross_brand_entry_rate")), 1e-9);
    assertEquals(0.075D, decimal(summary.get("recommendation_cross_brand_entry_rate")), 1e-9);
    assertEquals(0.035D, decimal(summary.get("banner_cross_brand_entry_rate")), 1e-9);
    assertEquals(0.375D, decimal(summary.get("recommendation_share_of_cross_brand_entries")), 1e-9);
    assertEquals("2026-09-10", day.get("event_date_kst"));

    Map<?, ?> filtered = (Map<?, ?>) service.crossBrandInflow(
      SELLER, BRAND, FROM, TO, "synthetic", "python_batch"
    ).get("summary");
    assertEquals(100L, number(filtered.get("brand_view_sessions")));
    assertEquals(20L, number(filtered.get("cross_brand_entry_sessions")));
    assertEquals(8L, number(filtered.get("recommendation_cross_brand_entry_sessions")));
    assertThrows(ResponseStatusException.class, () -> service.crossBrandInflow("other-seller", BRAND, FROM, TO, "all", "all"));
  }

  /* ---------------------------------------------------------------- E1 overview */

  @Test
  @DisplayName("개요 비율은 합산값에서 다시 계산한다 — 상세 진입은 노출 세션, 담기는 상세 세션이 분모")
  void overviewRecomputesRatesFromSums() {
    brandDay("2026-09-10", 100, 30, 50, 15, 10);
    brandDay("2026-09-11", 100, 30, 50, 15, 10);

    Map<String, Object> response = service.overview(SELLER, BRAND, FROM, TO, "all");
    Map<?, ?> current = (Map<?, ?>) response.get("current");

    assertEquals(200L, number(current.get("impression_sessions")));
    assertEquals(60L, number(current.get("detail_view_sessions")));
    assertEquals(0.3D, decimal(current.get("detail_entry_rate")), 1e-9);
    assertEquals(30D / 100D, decimal(current.get("information_view_rate")), 1e-9);
    assertEquals(20D / 60D, decimal(current.get("view_to_cart_rate")), 1e-9);
    assertEquals("full", coverage(response));
  }

  @Test
  @DisplayName("직전 기간에 행이 없으면 previous 는 0 이 아니라 null 이다")
  void overviewLeavesPreviousNullWhenNoRows() {
    brandDay("2026-09-10", 100, 30, 50, 15, 10);

    assertNull(service.overview(SELLER, BRAND, FROM, TO, "all").get("previous"));
  }

  @Test
  @DisplayName("일별 추이의 날짜는 문자열이다 — 숫자로 나가면 화면이 잘라 쓰다가 깨진다")
  void overviewDailyDatesAreText() {
    brandDay("2026-09-10", 100, 30, 50, 15, 10);

    List<?> daily = (List<?>) service.overview(SELLER, BRAND, FROM, TO, "all").get("daily");
    assertEquals("2026-09-10", ((Map<?, ?>) daily.getFirst()).get("event_date_kst"));
  }

  /* ---------------------------------------------------------------- E2 products */

  @Test
  @DisplayName("상품 CTR·상세 진입율의 분모는 세 노출 Event 합계다 (dw-schema §4.1)")
  void productDetailEntryRateDividesByImpressions() {
    productDay("2026-09-10", "P1", Map.of(
      "product_impression_count", 200,
      "recommendation_impression_count", 20,
      "banner_impression_count", 10,
      "impression_count", 230,
      "product_click_count", 50,
      "product_view_count", 40
    ));

    Map<?, ?> row = (Map<?, ?>) ((List<?>) service.products(SELLER, BRAND, FROM, TO, "all").get("products")).getFirst();

    assertEquals(50D / 230D, decimal(row.get("product_ctr")), 1e-9);
    assertEquals(40D / 230D, decimal(row.get("detail_entry_rate")), 1e-9);
  }

  @Test
  @DisplayName("이탈 지점은 기간을 합산한 뒤 최다를 고른다 — 하루치 최댓값을 집지 않는다")
  void topExitIsSummedOverTheRange() {
    productDay("2026-09-10", "P1", Map.of("product_view_sessions", 10));
    exitDay("2026-09-10", "P1", "user_review", 5);
    exitDay("2026-09-11", "P1", "user_review", 5);
    exitDay("2026-09-10", "P1", "ingredient_list", 8);

    Map<?, ?> row = (Map<?, ?>) ((List<?>) service.products(SELLER, BRAND, FROM, TO, "all").get("products")).getFirst();
    Map<?, ?> diagnostics = (Map<?, ?>) row.get("diagnostics");

    assertEquals("user_review", diagnostics.get("exit_content_kind_top"));
    assertEquals(10L, number(diagnostics.get("exit_sessions")));
  }

  @Test
  @DisplayName("진단할 재료가 하나도 없으면 블록은 null 이다 — 빈 객체는 화면이 실측 배지로 읽는다")
  void diagnosticsIsNullWhenNothingToShow() {
    productDay("2026-09-10", "P1", Map.of("product_impression_count", 10));

    Map<?, ?> row = (Map<?, ?>) ((List<?>) service.products(SELLER, BRAND, FROM, TO, "all").get("products")).getFirst();
    assertNull(row.get("diagnostics"));
  }

  @Test
  @DisplayName("보조 마트가 없어도 상품 블록은 살아 있고 coverage 가 partial 이 된다")
  void missingSideMartDegradesOneBlockOnly() {
    productDay("2026-09-10", "P1", Map.of("product_impression_count", 10, "product_view_sessions", 5, "variant_select_count", 10));
    dw.execute("drop table dw.product_exit_daily");
    dw.execute("drop table dw.funnel_daily_kpi");

    Map<String, Object> response = service.products(SELLER, BRAND, FROM, TO, "all");
    Map<?, ?> row = (Map<?, ?>) ((List<?>) response.get("products")).getFirst();

    assertEquals(1, ((List<?>) response.get("products")).size());
    assertNull(row.get("funnel"));
    assertNull(((Map<?, ?>) row.get("diagnostics")).get("exit_content_kind_top"));
    assertEquals(2D, decimal(((Map<?, ?>) row.get("diagnostics")).get("variant_select_per_session")), 1e-9);
    assertEquals("partial", coverage(response));
  }

  @Test
  @DisplayName("주 마트가 없으면 그때만 503 이다")
  void missingPrimaryMartIsUnavailable() {
    dw.execute("drop table dw.brand_daily_kpi");

    DashboardMartUnavailableException thrown = assertThrows(
      DashboardMartUnavailableException.class,
      () -> service.overview(SELLER, BRAND, FROM, TO, "all")
    );
    assertEquals("brand_daily_kpi", thrown.mart());
  }

  /* ---------------------------------------------------------------- E3 content */

  @Test
  @DisplayName("상품 조회 세션은 콘텐츠 종류·구역 축으로 합산하지 않는다 (계약 E3)")
  void contentDenominatorIsNotSummedAcrossKinds() {
    contentDay("2026-09-10", "P1", "ingredients", "ingredient_list", 100, 60, 600_000);
    contentDay("2026-09-10", "P1", "ingredients_more", "ingredient_list", 100, 10, 100_000);
    contentDay("2026-09-10", "P1", "reviews", "user_review", 100, 40, 400_000);

    List<?> rows = (List<?>) service.content(SELLER, BRAND, FROM, TO, "all").get("by_content_kind");
    Map<?, ?> ingredients = row(rows, "content_kind", "ingredient_list");

    assertEquals(100L, number(ingredients.get("product_view_sessions")));
    assertEquals(0.7D, decimal(ingredients.get("view_rate")), 1e-9);
    assertEquals(7_000D, decimal(ingredients.get("avg_dwell_ms_per_session")), 1e-9);
  }

  @Test
  @DisplayName("cart_lift 는 서버가 나눈다 — 본 사람의 담기율 / 브랜드 담기율")
  void cartLiftDividesByBrandRate() {
    brandDay("2026-09-10", 100, 60, 100, 30, 20);
    contentDay("2026-09-10", "P1", "ingredients", "ingredient_list", 100, 60, 600_000);
    insert("dw.content_conversion_daily", Map.of(
      "brand_id", BRAND, "event_date_kst", "2026-09-10", "product_id", "P1",
      "content_kind", "ingredient_list", "viewed_sessions", 50, "viewed_cart_sessions", 10
    ));

    Map<?, ?> conversion = (Map<?, ?>) row(
      (List<?>) service.content(SELLER, BRAND, FROM, TO, "all").get("by_content_kind"),
      "content_kind",
      "ingredient_list"
    ).get("conversion");

    assertEquals(0.2D, decimal(conversion.get("viewed_cart_rate")), 1e-9);
    // 브랜드 담기율 = 20/60 = 0.3333…
    assertEquals(0.2D / (20D / 60D), decimal(conversion.get("cart_lift")), 1e-9);
  }

  @Test
  @DisplayName("행동 대조는 두 프론트 판본이 읽는 이름을 모두 싣는다")
  void behaviorsCarryBothFieldNames() {
    contentDay("2026-09-10", "P1", "ingredients", "ingredient_list", 100, 60, 600_000);
    insert("dw.behavior_conversion_daily", Map.of(
      "brand_id", BRAND, "event_date_kst", "2026-09-10", "product_id", "P1", "event_name", "text_copy",
      "done_sessions", 100, "done_cart_sessions", 25, "not_done_sessions", 200, "not_done_cart_sessions", 20
    ));

    Map<?, ?> behavior = (Map<?, ?>) ((List<?>) service.content(SELLER, BRAND, FROM, TO, "all").get("behaviors")).getFirst();

    assertEquals(0.25D, decimal(behavior.get("done_cart_rate")), 1e-9);
    assertEquals(0.25D, decimal(behavior.get("cart_rate_with")), 1e-9);
    assertEquals(0.1D, decimal(behavior.get("not_done_cart_rate")), 1e-9);
    assertEquals(0.1D, decimal(behavior.get("cart_rate_without")), 1e-9);
  }

  @Test
  @DisplayName("브랜드 블록은 마트가 없어도 null 이 아니다 — 화면이 조건 없이 파고든다")
  void contentBrandBlockIsNeverNull() {
    contentDay("2026-09-10", "P1", "ingredients", "ingredient_list", 100, 60, 600_000);
    dw.execute("drop table dw.brand_daily_kpi");

    Map<String, Object> response = service.content(SELLER, BRAND, FROM, TO, "all");
    Map<?, ?> brandBlock = (Map<?, ?>) response.get("brand");

    assertNotNull(brandBlock);
    assertEquals(0L, number(brandBlock.get("product_view_sessions")));
    assertNull(brandBlock.get("view_to_cart_rate"));
    assertEquals("partial", coverage(response));
  }

  /* ---------------------------------------------------------------- E4 segments */

  @Test
  @DisplayName("관심 점수는 일별 평균을 다시 평균내지 않는다 — 세션 수로 가중한다")
  void interestScoreIsWeightedNotAveraged() {
    segmentDay("2026-09-10", "skin_type", "dry", 10, 1.0D);
    segmentDay("2026-09-11", "skin_type", "dry", 30, 5.0D);

    Map<?, ?> dry = row((List<?>) service.segments(SELLER, BRAND, FROM, TO, "all").get("by_segment"), "segment_value", "dry");

    // 단순 평균이면 3.0 이다. 세션 가중은 (1×10 + 5×30) / 40 = 4.0
    assertEquals(4.0D, decimal(dry.get("avg_interest_score")), 1e-9);
  }

  @Test
  @DisplayName("히트맵은 교차 축 행을 | 로 가른 것이다")
  void gridComesFromTheCrossAxis() {
    segmentDay("2026-09-10", "skin_type_x_skin_tone", "dry|fair", 10, 1.0D, 100, 120, 12);

    Map<?, ?> cell = (Map<?, ?>) ((List<?>) service.segments(SELLER, BRAND, FROM, TO, "all").get("grid")).getFirst();

    assertEquals("dry", cell.get("skin_type"));
    assertEquals("fair", cell.get("skin_tone"));
    assertEquals(12D / 120D, decimal(cell.get("view_to_cart_rate")), 1e-9);
  }

  @Test
  @DisplayName("체류 비중의 분모는 피부 타입 단위라 콘텐츠 종류로 합산하지 않는다")
  void dwellShareDenominatorIsNotSummedAcrossKinds() {
    segmentDay("2026-09-10", "skin_type", "dry", 10, 1.0D);
    segmentContentDay("2026-09-10", "dry", "ingredient_list", 600, 1000);
    segmentContentDay("2026-09-10", "dry", "user_review", 400, 1000);

    List<?> top = (List<?>) service.segments(SELLER, BRAND, FROM, TO, "all").get("top_content");

    assertEquals(0.6D, decimal(row(top, "content_kind", "ingredient_list").get("dwell_share")), 1e-9);
  }

  @Test
  @DisplayName("내 피부 타입 리뷰 필터 비율은 가를 축이 마트에 없어 비운다")
  void sameSkinFilterRateStaysNull() {
    segmentDay("2026-09-10", "skin_type", "dry", 10, 1.0D);

    assertNull(service.segments(SELLER, BRAND, FROM, TO, "all").get("same_skin_filter_rate"));
  }

  @Test
  @DisplayName("가격 블록은 가격 축을 유지한 채 기간을 합산하고 비율을 다시 계산한다")
  void priceBlocksKeepTheirAxesAndRecomputeRates() {
    priceBandDay("2026-09-10", "46k-66k", 100, 20, 10, 2, 1);
    priceBandDay("2026-09-11", "46k-66k", 200, 40, 30, 4, 3);
    segmentPriceDay("2026-09-10", "skin_type", "combination", "46k-66k", 100, 10, 2, 1);

    Map<String, Object> response = service.segments(SELLER, BRAND, FROM, TO, "all");
    Map<?, ?> price = ((List<Map<?, ?>>) response.get("price_bands")).getFirst();
    Map<?, ?> segmentPrice = ((List<Map<?, ?>>) response.get("segment_price_grid")).getFirst();

    assertEquals(300L, number(price.get("impression_sessions")));
    assertEquals(60L, number(price.get("detail_view_sessions")));
    assertEquals(6D / 60D, decimal(price.get("view_to_cart_rate")), 1e-9);
    assertEquals("combination", segmentPrice.get("segment_value"));
    assertEquals("46k-66k", segmentPrice.get("price_bin"));
    assertEquals(1D / 10D, decimal(segmentPrice.get("view_to_purchase_rate")), 1e-9);
  }

  @Test
  @DisplayName("코호트는 주간 행을 유지하고 억제된 분위값만 비운다")
  void cohortJoinsBrandDimensionAndPreservesSuppressedRows() {
    segmentDay("2026-09-10", "skin_type", "dry", 10, 1.0D);
    brandDay("2026-09-10", 100, 30, 50, 15, 10);
    brandDay("2026-09-11", 100, 30, 50, 15, 10);
    insert("dw.brand_cohort_dim", Map.of(
      "brand_id", BRAND,
      "brand_hash", "hash",
      "product_count", 2,
      "product_count_band", "2-3",
      "dominant_price_bin", "105k+",
      "cohort_key", "2-3|105k+",
      "commons_participating", true
    ));
    insert("dw.commons_cohort_weekly", Map.ofEntries(
      Map.entry("cohort_key", "2-3|105k+"),
      Map.entry("snapshot_week_kst", "2026-09-07"),
      Map.entry("metric_name", "view_to_cart_rate"),
      Map.entry("actor_type", "all"),
      Map.entry("window_start_date", "2026-09-07"),
      Map.entry("window_end_date", "2026-09-13"),
      Map.entry("brand_count", 4),
      Map.entry("is_suppressed", true),
      Map.entry("is_sample_sufficient", false),
      Map.entry("is_dominated", true),
      Map.entry("p25", 0.1D),
      Map.entry("p50", 0.2D),
      Map.entry("p75", 0.3D)
    ));

    Map<?, ?> cohort = (Map<?, ?>) service.segments(SELLER, BRAND, FROM, TO, "all").get("cohort");
    assertEquals(cohort, service.cohortPosition(SELLER, BRAND, FROM, TO, "all").get("cohort"));
    Map<?, ?> metric = ((List<Map<?, ?>>) cohort.get("metrics")).getFirst();

    assertEquals("2-3|105k+", cohort.get("cohort_key"));
    assertEquals("2026-09-07", cohort.get("snapshot_week_kst"));
    assertEquals(true, cohort.get("is_suppressed"));
    assertNull(metric.get("p25"));
    assertNull(metric.get("p50"));
    assertNull(metric.get("p75"));
    assertEquals(1D / 3D, decimal(metric.get("my_value")), 1e-9);
    assertNull(metric.get("my_position"));
  }

  @Test
  @DisplayName("actor=all 코호트는 분리된 전체 행의 분위값을 읽고 실행축 행을 합치지 않는다")
  void allActorCohortUsesMaterializedAllRow() {
    segmentDay("2026-09-10", "skin_type", "dry", 10, 1.0D);
    brandDay("2026-09-10", 100, 30, 50, 15, 10);
    insert("dw.brand_cohort_dim", Map.of(
      "brand_id", BRAND,
      "brand_hash", "hash",
      "product_count", 2,
      "product_count_band", "2-3",
      "cohort_key", "2-3|105k+",
      "commons_participating", true
    ));
    insertCohortMetric("web", 2, 0.1D, 0.2D, 0.3D);
    insertCohortMetric("synthetic", 6, 0.3D, 0.4D, 0.5D);
    insertCohortMetric("all", 5, 0.15D, 0.25D, 0.35D);

    Map<?, ?> cohort = (Map<?, ?>) service.segments(SELLER, BRAND, FROM, TO, "all").get("cohort");
    Map<?, ?> metric = ((List<Map<?, ?>>) cohort.get("metrics")).getFirst();

    assertEquals(5L, number(cohort.get("brand_count")));
    assertEquals(0.15D, decimal(metric.get("p25")), 1e-9);
    assertEquals(0.25D, decimal(metric.get("p50")), 1e-9);
    assertEquals(0.35D, decimal(metric.get("p75")), 1e-9);
    assertEquals(cohort, service.cohortPosition(SELLER, BRAND, FROM, TO, "all").get("cohort"));
  }

  /* ---------------------------------------------------------------- E5 ingredients */

  @Test
  @DisplayName("기간에 걸친 주를 포함한다 — 주는 KST 월요일이라 기간 시작이 주 중간이면 빠진다")
  void ingredientWeeksIncludeTheOverlappingWeek() {
    insert("dw.ingredient_weekly_interest", Map.of(
      "interest_week_kst", "2026-09-07", "ingredient_id", 12, "ingredient", "Niacinamide",
      "ingredient_interest_score", 300, "direct_match_score", 100, "product_attributed_score", 200
    ));
    insert("dw.ingredient_weekly_interest", Map.of(
      "interest_week_kst", "2026-09-07", "ingredient_id", 13, "ingredient", "Hyaluronic Acid",
      "ingredient_interest_score", 100, "direct_match_score", 50, "product_attributed_score", 50
    ));

    Map<String, Object> response = service.ingredients(SELLER, BRAND, FROM, TO, "all");

    assertEquals(List.of("2026-09-07"), response.get("weeks"));
    List<?> rows = (List<?>) response.get("by_ingredient");
    assertEquals(0.75D, decimal(row(rows, "ingredient", "Niacinamide").get("ingredient_interest_share")), 1e-9);
  }

  /* ---------------------------------------------------------------- E6 friction */

  @Test
  @DisplayName("세 마찰 Event 는 0 이어도 키가 남는다 — 0 인 것과 안 센 것은 다르다")
  void frictionCountsKeepZeroEvents() {
    insert("dw.friction_daily", Map.of(
      "brand_id", BRAND, "event_date_kst", "2026-09-10", "product_id", "P1",
      "section_id", "reviews", "event_name", "scroll_backtrack", "event_count", 40, "friction_sessions", 30
    ));
    dw.execute("drop table dw.event_daily");

    Map<String, Object> response = service.friction(SELLER, BRAND, FROM, TO, "all");
    Map<?, ?> counts = (Map<?, ?>) response.get("counts");

    assertEquals(40L, number(counts.get("scroll_backtrack")));
    assertEquals(0L, number(counts.get("dead_click")));
    assertEquals(0L, number(counts.get("rage_click")));
    assertNull(response.get("event_volumes"));
    assertEquals("partial", coverage(response));
    assertTrue(((List<?>) ((Map<?, ?>) response.get("source")).get("missing_marts")).contains("event_daily"));
  }

  /* ---------------------------------------------------------------- E7 purchase */

  @Test
  @DisplayName("재구매는 최신 스냅샷만 읽는다 — 스냅샷을 기간 합산하지 않는다")
  void repurchaseReadsTheLatestSnapshotOnly() {
    insert("dw.brand_repurchase_daily", Map.of(
      "brand_id", BRAND, "snapshot_date_kst", "2026-09-10", "buyer_count", 10, "repeat_buyer_count", 9,
      "median_days_between_purchases", 21.0
    ));
    insert("dw.brand_repurchase_daily", Map.of(
      "brand_id", BRAND, "snapshot_date_kst", "2026-09-11", "buyer_count", 100, "repeat_buyer_count", 20,
      "median_days_between_purchases", 21.0
    ));

    Map<?, ?> brandBlock = (Map<?, ?>) service.purchase(SELLER, BRAND, FROM, TO, "all").get("brand");

    assertEquals(100L, number(brandBlock.get("buyer_count")));
    assertEquals(0.2D, decimal(brandBlock.get("repurchase_rate")), 1e-9);
    assertEquals(21.0D, decimal(brandBlock.get("median_days_between_purchases")), 1e-9);
  }

  @Test
  @DisplayName("재구매 중앙값은 동일한 실행 축 행을 합쳐도 보존한다")
  void repurchaseKeepsMedianWhenExecutionAxisRowsAgree() {
    insert("dw.brand_repurchase_daily", Map.of(
      "brand_id", BRAND, "snapshot_date_kst", "2026-09-11", "buyer_count", 4,
      "repeat_buyer_count", 2, "median_days_between_purchases", 18.0,
      "actor_type", "user", "source", "web", "scenario_id", "scenario-a"
    ));
    insert("dw.brand_repurchase_daily", Map.of(
      "brand_id", BRAND, "snapshot_date_kst", "2026-09-11", "buyer_count", 6,
      "repeat_buyer_count", 3, "median_days_between_purchases", 18.0,
      "actor_type", "synthetic", "source", "simulator", "scenario_id", "scenario-b"
    ));

    Map<?, ?> brandBlock = (Map<?, ?>) service.purchase(SELLER, BRAND, FROM, TO, "all").get("brand");

    assertEquals(10L, number(brandBlock.get("buyer_count")));
    assertEquals(5L, number(brandBlock.get("repeat_buyer_count")));
    assertEquals(18.0D, decimal(brandBlock.get("median_days_between_purchases")), 1e-9);
  }

  @Test
  @DisplayName("재구매 고객이 있는 축의 중앙값은 재구매 고객이 없는 축의 NULL을 무시한다")
  void repurchaseIgnoresNullMedianFromAxisWithoutRepeatBuyer() {
    insert("dw.brand_repurchase_daily", Map.of(
      "brand_id", BRAND, "snapshot_date_kst", "2026-09-11", "buyer_count", 4,
      "repeat_buyer_count", 2, "median_days_between_purchases", 18.0,
      "actor_type", "user", "source", "web", "scenario_id", "scenario-a"
    ));
    Map<String, Object> noRepeat = new HashMap<>();
    noRepeat.put("brand_id", BRAND);
    noRepeat.put("snapshot_date_kst", "2026-09-11");
    noRepeat.put("buyer_count", 3);
    noRepeat.put("repeat_buyer_count", 0);
    noRepeat.put("median_days_between_purchases", null);
    noRepeat.put("actor_type", "synthetic");
    noRepeat.put("source", "simulator");
    noRepeat.put("scenario_id", "scenario-b");
    insert("dw.brand_repurchase_daily", noRepeat);

    Map<?, ?> brandBlock = (Map<?, ?>) service.purchase(SELLER, BRAND, FROM, TO, "all").get("brand");

    assertEquals(18.0D, decimal(brandBlock.get("median_days_between_purchases")), 1e-9);
  }

  @Test
  @DisplayName("재구매 고객이 없으면 중앙값은 NULL이다")
  void repurchaseMedianIsNullWhenNoAxisHasRepeatBuyer() {
    for (String actorType : List.of("user", "synthetic")) {
      Map<String, Object> row = new HashMap<>();
      row.put("brand_id", BRAND);
      row.put("snapshot_date_kst", "2026-09-11");
      row.put("buyer_count", 3);
      row.put("repeat_buyer_count", 0);
      row.put("median_days_between_purchases", null);
      row.put("actor_type", actorType);
      row.put("source", actorType.equals("user") ? "web" : "simulator");
      row.put("scenario_id", actorType);
      insert("dw.brand_repurchase_daily", row);
    }

    Map<?, ?> brandBlock = (Map<?, ?>) service.purchase(SELLER, BRAND, FROM, TO, "all").get("brand");

    assertNull(brandBlock.get("median_days_between_purchases"));
  }

  @Test
  @DisplayName("설문을 건너뛴 주문(reason NULL)은 사유 비중의 분모에서 뺀다")
  void skippedOrdersAreNotAReason() {
    Map<String, Object> restock = new LinkedHashMap<>(Map.of(
      "brand_id", BRAND, "event_date_kst", "2026-09-10", "order_count", 10, "primary_order_count", 8
    ));
    restock.put("reason", "restock");
    insert("dw.purchase_reason_daily", restock);
    Map<String, Object> skipped = new LinkedHashMap<>(Map.of(
      "brand_id", BRAND, "event_date_kst", "2026-09-10", "order_count", 90, "skipped_order_count", 90
    ));
    skipped.put("reason", null);
    insert("dw.purchase_reason_daily", skipped);

    List<?> reasons = (List<?>) service.purchase(SELLER, BRAND, FROM, TO, "all").get("reasons");

    assertEquals(1.0D, decimal(row(reasons, "reason", "restock").get("reason_share")), 1e-9);
    assertNull(row(reasons, "reason", null).get("reason_share"));
  }

  /* ---------------------------------------------------------------- 요청 해석 */

  @Test
  @DisplayName("잘못된 요청은 계약이 정한 400 문구로 거절한다")
  void rejectsBadRequests() {
    assertEquals("bad_actor_type", reasonOf(() -> service.overview(SELLER, BRAND, FROM, TO, "robot")));
    assertEquals("bad_range", reasonOf(() -> service.overview(SELLER, BRAND, "2026-09-12", "2026-09-11", "all")));
    assertEquals("bad_range", reasonOf(() -> service.overview(SELLER, BRAND, "어제", TO, "all")));
    assertEquals("range_too_long", reasonOf(() -> service.overview(SELLER, BRAND, "2026-01-01", "2026-09-11", "all")));
  }

  @Test
  @DisplayName("남의 브랜드는 마트를 읽기 전에 막는다")
  void refusesAnotherSellersBrand() {
    ResponseStatusException thrown = assertThrows(
      ResponseStatusException.class,
      () -> service.overview("seller-2", BRAND, FROM, TO, "all")
    );
    assertEquals(403, thrown.getStatusCode().value());
  }

  @Test
  @DisplayName("actorType 을 주면 그 축만 읽는다")
  void actorTypeFiltersTheMartKey() {
    brandDay("2026-09-10", 100, 30, 50, 15, 10, "web");
    brandDay("2026-09-10", 700, 70, 70, 70, 70, "synthetic");

    Map<?, ?> current = (Map<?, ?>) service.overview(SELLER, BRAND, FROM, TO, "web").get("current");
    assertEquals(100L, number(current.get("impression_sessions")));

    Map<?, ?> all = (Map<?, ?>) service.overview(SELLER, BRAND, FROM, TO, "all").get("current");
    assertEquals(800L, number(all.get("impression_sessions")));
  }

  @Test
  @DisplayName("계약 DDL 이 그대로 올라간다 — 조회가 읽는 컬럼이 마트에 있는지 확인하는 토대")
  void contractSchemaLoads() {
    assertFalse(DwTestSchema.statements().isEmpty());
    assertNotNull(dw.queryForObject("select count(*) from dw.brand_daily_kpi", Integer.class));
  }

  /* ---------------------------------------------------------------- 도우미 */

  private void brandDay(String date, int impressions, int detailViews, int productViews, int informationViews, int carts) {
    brandDay(date, impressions, detailViews, productViews, informationViews, carts, "web");
  }

  private void brandDay(
    String date,
    int impressions,
    int detailViews,
    int productViews,
    int informationViews,
    int carts,
    String actorType
  ) {
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("brand_id", BRAND);
    row.put("event_date_kst", date);
    row.put("actor_type", actorType);
    row.put("impression_sessions", impressions);
    row.put("detail_view_sessions", detailViews);
    row.put("product_view_sessions", productViews);
    row.put("information_view_sessions", informationViews);
    row.put("add_to_cart_sessions", carts);
    row.put("unique_user_count", productViews);
    insert("dw.brand_daily_kpi", row);
  }

  private void productDay(String date, String productId, Map<String, Object> metrics) {
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("brand_id", BRAND);
    row.put("event_date_kst", date);
    row.put("product_id", productId);
    row.put("actor_type", "web");
    row.putAll(metrics);
    insert("dw.product_daily_kpi", row);
  }

  private void exitDay(String date, String productId, String contentKind, int sessions) {
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("brand_id", BRAND);
    row.put("event_date_kst", date);
    row.put("product_id", productId);
    row.put("last_content_kind", contentKind);
    row.put("actor_type", "web");
    row.put("exit_sessions", sessions);
    insert("dw.product_exit_daily", row);
  }

  private void contentDay(
    String date,
    String productId,
    String sectionId,
    String contentKind,
    int productViewSessions,
    int sectionViewSessions,
    int dwellMs
  ) {
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("brand_id", BRAND);
    row.put("event_date_kst", date);
    row.put("product_id", productId);
    row.put("section_id", sectionId);
    row.put("content_kind", contentKind);
    row.put("actor_type", "web");
    row.put("product_view_sessions", productViewSessions);
    row.put("section_view_sessions", sectionViewSessions);
    row.put("section_view_count", sectionViewSessions);
    row.put("dwell_ms_sum", dwellMs);
    insert("dw.content_daily_kpi", row);
  }

  private void segmentDay(String date, String type, String value, int sessions, double interest) {
    segmentDay(date, type, value, sessions, interest, sessions, sessions, 0);
  }

  private void segmentDay(
    String date,
    String type,
    String value,
    int sessions,
    double interest,
    int productViewSessions,
    int detailViewSessions,
    int carts
  ) {
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("brand_id", BRAND);
    row.put("event_date_kst", date);
    row.put("segment_type", type);
    row.put("segment_value", value);
    row.put("actor_type", "web");
    row.put("session_count", sessions);
    row.put("segment_user_count", sessions);
    row.put("product_view_sessions", productViewSessions);
    row.put("detail_view_sessions", detailViewSessions);
    row.put("add_to_cart_sessions", carts);
    row.put("avg_interest_score", interest);
    insert("dw.persona_segment_daily_kpi", row);
  }

  private void segmentContentDay(String date, String skinType, String contentKind, int dwell, int segmentDwell) {
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("brand_id", BRAND);
    row.put("event_date_kst", date);
    row.put("skin_type", skinType);
    row.put("content_kind", contentKind);
    row.put("actor_type", "web");
    row.put("dwell_ms_sum", dwell);
    row.put("dwell_sessions", 1);
    row.put("segment_dwell_ms_sum", segmentDwell);
    insert("dw.segment_content_daily", row);
  }

  private void priceBandDay(String date, String priceBin, int impressions, int detailViews, int productViews, int carts, int purchases) {
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("brand_id", BRAND);
    row.put("event_date_kst", date);
    row.put("price_bin", priceBin);
    row.put("currency", "KRW");
    row.put("actor_type", "web");
    row.put("session_count", impressions);
    row.put("unique_user_count", productViews);
    row.put("impression_sessions", impressions);
    row.put("quick_look_sessions", 0);
    row.put("product_view_sessions", productViews);
    row.put("detail_view_sessions", detailViews);
    row.put("add_to_cart_sessions", carts);
    row.put("purchase_sessions", purchases);
    row.put("product_count", 1);
    insert("dw.brand_price_band_daily_kpi", row);
  }

  private void segmentPriceDay(String date, String type, String value, String priceBin, int sessions, int detailViews, int carts, int purchases) {
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("brand_id", BRAND);
    row.put("event_date_kst", date);
    row.put("segment_type", type);
    row.put("segment_value", value);
    row.put("price_bin", priceBin);
    row.put("currency", "KRW");
    row.put("actor_type", "web");
    row.put("segment_user_count", sessions);
    row.put("session_count", sessions);
    row.put("product_view_sessions", sessions);
    row.put("detail_view_sessions", detailViews);
    row.put("add_to_cart_sessions", carts);
    row.put("purchase_sessions", purchases);
    row.put("product_count", 1);
    insert("dw.segment_price_band_daily_kpi", row);
  }

  private void insertCohortMetric(String actorType, int brandCount, double p25, double p50, double p75) {
    insert("dw.commons_cohort_weekly", Map.ofEntries(
      Map.entry("cohort_key", "2-3|105k+"),
      Map.entry("snapshot_week_kst", "2026-09-07"),
      Map.entry("metric_name", "view_to_cart_rate"),
      Map.entry("actor_type", actorType),
      Map.entry("window_start_date", "2026-09-07"),
      Map.entry("window_end_date", "2026-09-13"),
      Map.entry("brand_count", brandCount),
      Map.entry("is_suppressed", false),
      Map.entry("is_sample_sufficient", true),
      Map.entry("is_dominated", false),
      Map.entry("p25", p25),
      Map.entry("p50", p50),
      Map.entry("p75", p75)
    ));
  }

  private void insert(String table, Map<String, Object> values) {
    List<String> columns = new ArrayList<>(values.keySet());
    String placeholders = String.join(",", columns.stream().map(c -> "?").toList());
    dw.update(
      "insert into " + table + " (" + String.join(",", columns) + ") values (" + placeholders + ")",
      columns.stream().map(values::get).toArray()
    );
  }

  private static DashboardMartJdbcProvider provider(JdbcTemplate jdbc) {
    return new DashboardMartJdbcProvider("jdbc:h2:mem:unused", "sa", "dw-test") {
      @Override
      public JdbcTemplate jdbc() {
        return jdbc;
      }
    };
  }

  private static String coverage(Map<String, Object> response) {
    return String.valueOf(((Map<?, ?>) response.get("source")).get("coverage"));
  }

  private static Map<?, ?> row(List<?> rows, String key, Object value) {
    for (Object item : rows) {
      Map<?, ?> row = (Map<?, ?>) item;
      if (value == null ? row.get(key) == null : value.equals(row.get(key))) return row;
    }
    throw new AssertionError(key + "=" + value + " 행이 없다: " + rows);
  }

  private static long number(Object value) {
    return ((Number) value).longValue();
  }

  private static double decimal(Object value) {
    return ((Number) value).doubleValue();
  }

  private static String reasonOf(Runnable call) {
    ResponseStatusException thrown = assertThrows(ResponseStatusException.class, call::run);
    return thrown.getReason();
  }
}
