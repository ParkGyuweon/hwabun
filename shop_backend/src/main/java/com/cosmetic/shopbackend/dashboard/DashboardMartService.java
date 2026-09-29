package com.cosmetic.shopbackend.dashboard;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Date;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Supplier;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

/**
 * 브랜드 대시보드 마트 조회 (계약 `contracts/dashboard-mart-api-spec.md`).
 *
 * 집계된 마트만 읽는다. 개별 고객의 행을 내보내지 않고, 다른 브랜드 값도 섞지 않는다 (계약 §1-5 A층).
 *
 * <h2>블록 단위로 물러난다</h2>
 * 한 엔드포인트가 여러 마트를 읽는다. 그중 하나가 아직 projection 되지 않았다고 해서 **엔드포인트 전체를 503 으로
 * 떨어뜨리면 안 된다** — 있는 마트까지 같이 죽어 화면이 통째로 모의로 돌아간다. 그래서 보조 마트는
 * {@link Read#optional} 로 읽고, 없으면 그 블록만 `null` 이며 `coverage` 가 `partial` 이 된다 (계약 §1-3).
 * 주 마트가 없을 때만 503 `mart_unavailable` 이다 (§1-4).
 *
 * <h2>비율은 합산값에서 다시 계산한다</h2>
 * 일별 비율을 평균내지 않는다 (계약 §1-3). 분모가 0 이면 `null` 이다. 분모가 무엇인지는 `dw-schema.md` §4 가
 * 정본이라 이 파일은 그 정의를 그대로 옮긴다 — 이름이 같아도 마트마다 분모가 다른 것이 있다 (§4.1 vs §4.14).
 */
@Service
public class DashboardMartService {

  private static final ZoneId KST = ZoneId.of("Asia/Seoul");
  /**
   * DW 의 `actor_type` 은 `user` · `synthetic` 두 값뿐이다 (clean_events_job). `all` 은 필터를 걸지 않는 조회값이다.
   * `web` 은 `user` 의 예전 이름이라 받아서 `user` 로 바꾼다 (계약 §1-2).
   */
  private static final Set<String> ACTOR_TYPES = Set.of("all", "user", "synthetic");
  private static final String LEGACY_USER_ACTOR = "web";
  private static final Pattern DW_TABLE = Pattern.compile("dw\\.([a-z_]+)");

  /** 계약 §1-2. 넘으면 400 range_too_long */
  private static final int MAX_RANGE_DAYS = 92;

  /** 계약 §1-2 기본 기간 (to 포함 14일) */
  private static final int DEFAULT_RANGE_DAYS = 14;

  /** DW 연결 자체가 설정되지 않았을 때의 마트 이름. 블록 단위로 물러날 여지가 없어 그대로 503 이다 */
  private static final String NO_CONNECTION = "dw_connection";

  /**
   * 마트 key 중 집계에서 걷어내는 축. `source`·`scenario_id`·`simulation_run_id` 는 전부 합산하고(계약 §1-2),
   * 나머지는 "한 행에 같은 값이 반복되는" 컬럼을 되살릴 때 group by 에 그대로 쓴다.
   */
  private static final String EXECUTION_AXES =
    "actor_type,source,generator_type,scenario_id,simulation_run_id";

  private final JdbcTemplate shopJdbc;
  private final DashboardMartJdbcProvider martJdbc;

  public DashboardMartService(JdbcTemplate shopJdbc, DashboardMartJdbcProvider martJdbc) {
    this.shopJdbc = shopJdbc;
    this.martJdbc = martJdbc;
  }

  /* ------------------------------------------------------------------ 기존 4칸 요약 */

  public Map<String, Object> commerceSummary(String sellerId, String brandId) {
    owns(sellerId, brandId);
    return shopJdbc.queryForMap(
      "select count(distinct oi.order_id) orders," +
        "coalesce(sum(oi.line_amount),0) revenue," +
        // 팔린 개수는 주문 수와 다르다. 한 주문에 같은 상품 3개가 들어가면 주문 1, 수량 3 이다.
        "coalesce(sum(oi.quantity),0) units," +
        // 몇 가지가 팔렸나. 한 상품만 여러 번 팔린 것과 여러 상품이 골고루 팔린 것은 다른 이야기다
        "count(distinct oi.product_id) sold_products," +
        // 주문 줄 수. 주문 수와 상품 종류 사이를 메우는 값이라 같이 낸다
        "count(*) order_items," +
        "(select count(*) from review r join order_item x on x.order_item_id=r.order_item_id where x.brand_id=?) reviews," +
        "(select count(*) from feedback f join product x on x.product_id=f.product_id where x.brand_id=? and f.status='VISIBLE') feedbacks " +
        "from order_item oi join shop_order o on o.order_id=oi.order_id where oi.brand_id=? and o.status='PAID'",
      brandId,
      brandId,
      brandId
    );
  }

  /** Compare each active product's list price with its category median. */
  public Map<String, Object> pricePosition(String seller, String brand) {
    owns(seller, brand);
    // This is a live shop-catalog comparison, not the Parquet-only
    // category_price_reference Mart. Its snapshot and prices may differ.
    List<Map<String, Object>> catalog = shopJdbc.queryForList(
      "select p.product_id,p.brand_id,p.product_name,p.secondary_category," +
        "min(case when v.status='ACTIVE' and v.price_krw>0 then v.price_krw end) price_krw " +
        "from product p left join product_variant v on v.product_id=p.product_id " +
        "where p.status='ACTIVE' " +
        "group by p.product_id,p.brand_id,p.product_name,p.secondary_category order by p.product_id"
    );
    Map<String, List<BigDecimal>> pricesByCategory = new LinkedHashMap<>();
    List<BigDecimal> allPrices = new ArrayList<>();
    for (Map<String, Object> product : catalog) {
      BigDecimal price = decimalOrNull(product.get("price_krw"));
      if (price == null) continue;
      pricesByCategory.computeIfAbsent(String.valueOf(product.get("secondary_category")), ignored -> new ArrayList<>()).add(price);
      allPrices.add(price);
    }
    BigDecimal globalMedian = median(allPrices);
    List<Map<String, Object>> comparisons = new ArrayList<>();
    for (Map<String, Object> product : catalog) {
      if (!brand.equals(product.get("brand_id"))) continue;
      List<BigDecimal> categoryPrices = pricesByCategory.getOrDefault(String.valueOf(product.get("secondary_category")), List.of());
      boolean sufficient = categoryPrices.size() >= 3;
      BigDecimal price = decimalOrNull(product.get("price_krw"));
      BigDecimal categoryMedian = median(categoryPrices);
      BigDecimal reference = sufficient ? categoryMedian : globalMedian;
      Map<String, Object> row = new LinkedHashMap<>(product);
      row.remove("brand_id");
      row.put("currency", "KRW");
      row.put("category_product_count", categoryPrices.size());
      row.put("category_median_krw", categoryMedian);
      row.put("reference_median_krw", reference);
      row.put("reference_source", sufficient ? "category" : "global_fallback");
      row.put("is_sample_sufficient", sufficient);
      row.put("price_difference_pct", price == null || reference == null || reference.signum() <= 0 ? null :
        price.subtract(reference).multiply(BigDecimal.valueOf(100)).divide(reference, 2, RoundingMode.HALF_UP));
      comparisons.add(row);
    }
    Map<String, Object> response = new LinkedHashMap<>();
    response.put("brand_id", brand);
    response.put("currency", "KRW");
    response.put("products", comparisons);
    return response;
  }

  private static BigDecimal median(List<BigDecimal> values) {
    if (values.isEmpty()) return null;
    List<BigDecimal> sorted = new ArrayList<>(values);
    Collections.sort(sorted);
    int middle = sorted.size() / 2;
    return sorted.size() % 2 == 1 ? sorted.get(middle) :
      sorted.get(middle - 1).add(sorted.get(middle)).divide(BigDecimal.valueOf(2), 2, RoundingMode.HALF_UP);
  }

  private static BigDecimal decimalOrNull(Object value) {
    return value == null ? null : new BigDecimal(value.toString());
  }

  /** Expose the same anonymized cohort position used by the segments dashboard. */
  public Map<String, Object> cohortPosition(String seller, String brand, String from, String to, String actor) {
    Read read = open(seller, brand, from, to, actor);
    CohortResult result = read.optional("brand_cohort_dim", () -> cohort(read, read.q));
    Map<String, Object> body = new LinkedHashMap<>();
    body.put("cohort", result == null ? null : result.body());
    return read.envelope(
      List.of("brand_cohort_dim", "commons_cohort_weekly", "brand_daily_kpi"),
      result != null,
      result == null ? null : result.processedAt(),
      body
    );
  }

  /** Cross-brand entry sessions for the seller's destination brand. */
  public Map<String, Object> crossBrandInflow(
    String seller,
    String brand,
    String from,
    String to,
    String actor,
    String generatorType
  ) {
    Read read = open(seller, brand, from, to, actor);
    String generator = generatorType == null || generatorType.isBlank() ? "all" : generatorType;
    List<Map<String, Object>> daily = read.optional("cross_brand_daily", () -> crossBrandDaily(read.q, generator));

    Map<String, Object> body = new LinkedHashMap<>();
    body.put("summary", daily == null || daily.isEmpty() ? null : crossBrandSummary(daily));
    body.put("daily", daily);
    Object processedAt = null;
    if (daily != null) {
      for (Map<String, Object> row : daily) {
        Object candidate = row.remove("mart_processed_at");
        if (candidate instanceof Timestamp timestamp &&
          (!(processedAt instanceof Timestamp current) || timestamp.after(current))) {
          processedAt = timestamp;
        }
        row.put("event_date_kst", dateText(row.get("event_date_kst")));
        row.put("cross_brand_entry_rate", divide(row.get("cross_brand_entry_sessions"), row.get("brand_view_sessions")));
        row.put("recommendation_cross_brand_entry_rate", divide(
          row.get("recommendation_cross_brand_entry_sessions"), row.get("brand_view_sessions")
        ));
        row.put("banner_cross_brand_entry_rate", divide(
          row.get("banner_cross_brand_entry_sessions"), row.get("brand_view_sessions")
        ));
        row.put("recommendation_share_of_cross_brand_entries", divide(
          row.get("recommendation_cross_brand_entry_sessions"), row.get("cross_brand_entry_sessions")
        ));
        row.put("banner_share_of_cross_brand_entries", divide(
          row.get("banner_cross_brand_entry_sessions"), row.get("cross_brand_entry_sessions")
        ));
      }
    }
    return read.envelope(
      List.of("cross_brand_daily"),
      daily != null && !daily.isEmpty(),
      processedAt,
      body
    );
  }

  private List<Map<String, Object>> crossBrandDaily(Query q, String generatorType) {
    String actorClause = "all".equals(q.actor()) ? "" : " and actor_type=?";
    String generatorClause = "all".equals(generatorType) ? "" : " and generator_type=?";
    List<Object> args = new ArrayList<>(List.of(q.brand(), Date.valueOf(q.from()), Date.valueOf(q.to())));
    if (!actorClause.isEmpty()) args.add(q.actor());
    if (!generatorClause.isEmpty()) args.add(generatorType);
    return many(
      "select event_date_kst," +
        "coalesce(sum(brand_view_sessions),0) brand_view_sessions," +
        "coalesce(sum(cross_brand_entry_sessions),0) cross_brand_entry_sessions," +
        "coalesce(sum(recommendation_cross_brand_entry_sessions),0) recommendation_cross_brand_entry_sessions," +
        "coalesce(sum(banner_cross_brand_entry_sessions),0) banner_cross_brand_entry_sessions," +
        "max(mart_processed_at) mart_processed_at " +
        "from dw.cross_brand_daily where destination_brand_id=? and event_date_kst between ? and ?" +
        actorClause + generatorClause + " group by event_date_kst order by event_date_kst",
      args.toArray()
    );
  }

  private Map<String, Object> crossBrandSummary(List<Map<String, Object>> daily) {
    Map<String, Object> summary = new LinkedHashMap<>();
    for (String field : List.of(
      "brand_view_sessions",
      "cross_brand_entry_sessions",
      "recommendation_cross_brand_entry_sessions",
      "banner_cross_brand_entry_sessions"
    )) {
      summary.put(field, daily.stream().mapToLong(row -> longOf(row.get(field))).sum());
    }
    summary.put("cross_brand_entry_rate", divide(summary.get("cross_brand_entry_sessions"), summary.get("brand_view_sessions")));
    summary.put("recommendation_cross_brand_entry_rate", divide(
      summary.get("recommendation_cross_brand_entry_sessions"), summary.get("brand_view_sessions")
    ));
    summary.put("banner_cross_brand_entry_rate", divide(
      summary.get("banner_cross_brand_entry_sessions"), summary.get("brand_view_sessions")
    ));
    summary.put("recommendation_share_of_cross_brand_entries", divide(
      summary.get("recommendation_cross_brand_entry_sessions"), summary.get("cross_brand_entry_sessions")
    ));
    summary.put("banner_share_of_cross_brand_entries", divide(
      summary.get("banner_cross_brand_entry_sessions"), summary.get("cross_brand_entry_sessions")
    ));
    return summary;
  }

  /* ------------------------------------------------------------------ E1 overview */

  public Map<String, Object> overview(String seller, String brand, String from, String to, String actor) {
    Read read = open(seller, brand, from, to, actor);
    Query q = read.q;

    Map<String, Object> current = read.required("brand_daily_kpi", () -> one(brandPeriodSql(q), q.args()));
    long rows = longOf(current.remove("row_count"));
    Object processedAt = current.remove("mart_processed_at");
    mergeProductTotals(read, q, current);

    Query previousRange = q.previous();
    Map<String, Object> previous = read.required(
      "brand_daily_kpi",
      () -> one(brandPeriodSql(previousRange), previousRange.args())
    );
    // 직전 기간에 행이 없으면 0 이 아니라 `null` 이다. 0 을 내보내면 화면이 "−100%" 라는 없는 변화를 그린다.
    boolean hasPrevious = longOf(previous.remove("row_count")) > 0;
    previous.remove("mart_processed_at");
    if (hasPrevious) mergeProductTotals(read, previousRange, previous);

    // unique_user_count 는 마트 행(하루 × 실행 축)마다 따로 센 고유 사용자 수다. 여기서는 같은 날의 실행 축 행을 더할 뿐이라
    // 축을 걸쳐 같은 사용자가 있으면 두 번 들어간다. 사람 수로 화면에 내지 않는다.
    List<Map<String, Object>> daily = read.required(
      "brand_daily_kpi",
      () ->
        many(
          "select event_date_kst,coalesce(sum(product_view_sessions),0) product_view_sessions," +
            "coalesce(sum(add_to_cart_sessions),0) add_to_cart_sessions," +
            "coalesce(sum(unique_user_count),0) unique_user_count " +
            "from dw.brand_daily_kpi where " + q.where("event_date_kst") +
            " group by event_date_kst order by event_date_kst",
          q.args()
        )
    );
    for (Map<String, Object> day : daily) day.put("event_date_kst", dateText(day.get("event_date_kst")));

    // 퍼널은 상품 합산이라 브랜드 세션 dedup 이 아니다 (계약 E1). 마트가 없으면 이 블록만 비운다.
    Map<String, Object> funnel = read.optional(
      "funnel_daily_kpi",
      () ->
        nullIfNoRows(
          one(
            "select coalesce(sum(impression_sessions),0) impression_sessions," +
              "coalesce(sum(click_sessions),0) click_sessions," +
              "coalesce(sum(quick_look_sessions),0) quick_look_sessions," +
              "coalesce(sum(quick_look_cart_sessions),0) quick_look_cart_sessions," +
              "coalesce(sum(product_view_sessions),0) product_view_sessions," +
              "coalesce(sum(detail_view_sessions),0) detail_view_sessions," +
              "coalesce(sum(information_view_sessions),0) information_view_sessions," +
              "coalesce(sum(add_to_cart_sessions),0) add_to_cart_sessions," +
              "coalesce(sum(checkout_sessions),0) checkout_sessions," +
              "coalesce(sum(purchase_sessions),0) purchase_sessions,count(*) row_count " +
              "from dw.funnel_daily_kpi where " + q.where("funnel_date_kst"),
            q.args()
          )
        )
    );

    Map<String, Object> body = new LinkedHashMap<>();
    body.put("current", current);
    body.put("previous", hasPrevious ? previous : null);
    body.put("daily", daily);
    body.put("funnel", funnel);
    return read.envelope(List.of("brand_daily_kpi", "product_daily_kpi", "funnel_daily_kpi"), rows > 0, processedAt, body);
  }

  /**
   * `brand_daily_kpi` 기간 합산. 비율은 `dw-schema.md` §4.14 의 분모 그대로다 —
   * 상세 진입은 `detail_view_sessions / impression_sessions`(상세 ∪ 퀵룩), 담기는 `/ detail_view_sessions` 다.
   */
  private static String brandPeriodSql(Query q) {
    // unique_user_count 는 **하루 단위로 센 고유 사용자 수의 합**이다. 마트가 날짜별 고유 수만 가지므로 기간 합산은
    // 여러 날 들른 같은 사용자를 날마다 다시 센다 — 기간의 고유 사용자 수가 아니다. 화면은 이 값을 "명" 으로 쓰지 않는다.
    return "select coalesce(sum(impression_sessions),0) impression_sessions," +
      "coalesce(sum(product_view_sessions),0) product_view_sessions," +
      "coalesce(sum(information_view_sessions),0) information_view_sessions," +
      "coalesce(sum(add_to_cart_sessions),0) add_to_cart_sessions," +
      "coalesce(sum(detail_view_sessions),0) detail_view_sessions," +
      "coalesce(sum(unique_user_count),0) unique_user_count," +
      "coalesce(sum(product_count_viewed),0) product_count_viewed," +
      ratio("detail_view_sessions", "impression_sessions", "detail_entry_rate") + "," +
      ratio("information_view_sessions", "product_view_sessions", "information_view_rate") + "," +
      ratio("add_to_cart_sessions", "detail_view_sessions", "view_to_cart_rate") + "," +
      "min(mart_processed_at) mart_processed_at,count(*) row_count " +
      "from dw.brand_daily_kpi where " + q.where("event_date_kst");
  }

  /**
   * 담았다 뺀 비율의 분자·분모는 상품 마트에서 온다 (계약 E1). `add_to_cart_sessions_by_product` 는 상품 합산이라
   * `brand_daily_kpi` 의 같은 이름 컬럼과 값이 다르다 — 그래서 이름을 다르게 둔다.
   *
   * 상품 마트가 없으면 이 다섯 칸은 0 이다. 키 자체를 빼면 화면이 `undefined` 를 계산에 넣는다.
   */
  private void mergeProductTotals(Read read, Query q, Map<String, Object> target) {
    Map<String, Object> totals = read.optional(
      "product_daily_kpi",
      () ->
        one(
          "select coalesce(sum(product_view_count),0) product_view_count," +
            "coalesce(sum(add_to_cart_count),0) add_to_cart_count," +
            "coalesce(sum(remove_from_cart_count),0) remove_from_cart_count," +
            "coalesce(sum(add_to_cart_sessions),0) add_to_cart_sessions_by_product," +
            "coalesce(sum(remove_from_cart_sessions),0) remove_from_cart_sessions," +
            "coalesce(sum(purchase_sessions),0) purchase_sessions," +
            "coalesce(sum(purchase_count),0) purchase_count," +
            "coalesce(sum(purchase_quantity),0) purchase_quantity," +
            ratio("remove_from_cart_sessions", "add_to_cart_sessions", "removal_rate") +
            " from dw.product_daily_kpi where " + q.where("event_date_kst"),
          q.args()
        )
    );
    if (totals == null) {
      for (String key : List.of(
        "product_view_count",
        "add_to_cart_count",
        "remove_from_cart_count",
        "add_to_cart_sessions_by_product",
        "remove_from_cart_sessions",
        "purchase_sessions",
        "purchase_count",
        "purchase_quantity"
      )) target.put(key, 0L);
      target.put("removal_rate", null);
      return;
    }
    target.putAll(totals);
  }

  /* ------------------------------------------------------------------ E2 products */

  public Map<String, Object> products(String seller, String brand, String from, String to, String actor) {
    Read read = open(seller, brand, from, to, actor);
    Query q = read.q;

    List<Map<String, Object>> products = read.required(
      "product_daily_kpi",
      () ->
        many(
          "select product_id,coalesce(sum(product_impression_count),0) product_impression_count," +
            "coalesce(sum(product_click_count),0) product_click_count," +
            "coalesce(sum(quick_look_count),0) quick_look_count," +
            "coalesce(sum(product_view_count),0) product_view_count," +
            "coalesce(sum(add_to_cart_count),0) add_to_cart_count," +
            "coalesce(sum(remove_from_cart_count),0) remove_from_cart_count," +
            "coalesce(sum(variant_select_count),0) variant_select_count," +
            "coalesce(sum(quick_look_close_open_detail_count),0) quick_look_close_open_detail_count," +
            "coalesce(sum(quick_look_sessions),0) quick_look_sessions," +
            "coalesce(sum(product_view_sessions),0) product_view_sessions," +
            "coalesce(sum(detail_view_sessions),0) detail_view_sessions," +
            "coalesce(sum(add_to_cart_sessions),0) add_to_cart_sessions," +
            "coalesce(sum(remove_from_cart_sessions),0) remove_from_cart_sessions," +
            "coalesce(sum(session_count),0) session_count," +
            // 하루 단위로 센 고유 사용자 수를 기간 동안 더한 값이다. 여러 날 본 같은 사용자가 날마다 들어가 고유 수가 아니다.
            "coalesce(sum(unique_user_count),0) unique_user_count," +
            "coalesce(sum(product_interest_score),0) product_interest_score," +
            // §4.1: product_ctr · detail_entry_rate 의 분모는 세 노출 합계인 impression_count(Event 수)다. 세션이 아니다.
            ratio("product_click_count", "impression_count", "product_ctr") + "," +
            ratio("product_view_count", "impression_count", "detail_entry_rate") + "," +
            // §4.1: 담기율 분모는 detail_view_sessions. product_view_sessions 로 나누면 1.0 을 넘는다 (Jira 277).
            ratio("add_to_cart_sessions", "detail_view_sessions", "add_to_cart_rate") + "," +
            "min(mart_processed_at) mart_processed_at " +
            "from dw.product_daily_kpi where " + q.where("event_date_kst") + " group by product_id",
          q.args()
        )
    );
    Object processedAt = products.stream().map(p -> p.get("mart_processed_at")).filter(x -> x != null).findFirst().orElse(null);
    for (Map<String, Object> product : products) product.remove("mart_processed_at");

    Map<String, Map<String, Object>> funnels = read.optional(
      "funnel_daily_kpi",
      () ->
        indexed(
          many(
            "select product_id,coalesce(sum(impression_sessions),0) impression_sessions," +
              "coalesce(sum(click_sessions),0) click_sessions," +
              "coalesce(sum(quick_look_sessions),0) quick_look_sessions," +
              "coalesce(sum(quick_look_cart_sessions),0) quick_look_cart_sessions," +
              "coalesce(sum(product_view_sessions),0) product_view_sessions," +
              "coalesce(sum(detail_view_sessions),0) detail_view_sessions," +
              "coalesce(sum(information_view_sessions),0) information_view_sessions," +
              "coalesce(sum(add_to_cart_sessions),0) add_to_cart_sessions " +
              "from dw.funnel_daily_kpi where " + q.where("funnel_date_kst") + " group by product_id",
            q.args()
          ),
          "product_id"
        )
    );

    // 이탈 지점은 기간을 **합산한 뒤** 최다 콘텐츠를 고른다. 일별 최댓값 행을 그대로 집으면
    // 하루치 우연이 기간 전체의 대표값이 된다.
    Map<String, Map<String, Object>> exits = read.optional("product_exit_daily", () -> topExits(q));

    for (Map<String, Object> product : products) {
      String id = String.valueOf(product.get("product_id"));
      product.put("funnel", funnels == null ? null : funnels.get(id));
      product.put("diagnostics", diagnostics(product, exits == null ? null : exits.get(id), exits != null));
      product.remove("variant_select_count");
      product.remove("quick_look_close_open_detail_count");
    }
    return read.envelope(
      List.of("product_daily_kpi", "funnel_daily_kpi", "product_exit_daily"),
      !products.isEmpty(),
      processedAt,
      Map.of("products", products)
    );
  }

  private Map<String, Map<String, Object>> topExits(Query q) {
    List<Map<String, Object>> rows = many(
      "select product_id,last_content_kind,coalesce(sum(exit_sessions),0) exit_sessions " +
        "from dw.product_exit_daily where " + q.where("event_date_kst") +
        " group by product_id,last_content_kind",
      q.args()
    );
    Map<String, Map<String, Object>> best = new LinkedHashMap<>();
    for (Map<String, Object> row : rows) {
      String id = String.valueOf(row.get("product_id"));
      Map<String, Object> current = best.get(id);
      if (current == null || longOf(row.get("exit_sessions")) > longOf(current.get("exit_sessions"))) best.put(id, row);
    }
    return best;
  }

  /**
   * 진단 3열. 계약 E2 의 두 비율은 서버가 나눈다 —
   * `variant_select_per_session = variant_select_count / product_view_sessions`,
   * `quick_look_open_detail_rate = quick_look_close_open_detail_count / quick_look_sessions`. 분모 0 이면 null.
   *
   * **전부 비어 있으면 블록 자체를 null 로 준다.** 값이 하나도 없는데 객체를 내보내면 화면이 이 블록을 "실측" 으로
   * 표시한다 (`martAdapter` 는 `diagnostics != null` 을 실측 판정에 쓴다).
   */
  private Map<String, Object> diagnostics(Map<String, Object> product, Map<String, Object> exit, boolean exitMartPresent) {
    Double variants = divide(product.get("variant_select_count"), product.get("product_view_sessions"));
    Double quickLook = divide(product.get("quick_look_close_open_detail_count"), product.get("quick_look_sessions"));
    Object topKind = exit == null ? null : exit.get("last_content_kind");
    if (topKind == null && variants == null && quickLook == null) return null;
    Long exitSessions;
    if (exit != null) exitSessions = longOf(exit.get("exit_sessions"));
    else if (exitMartPresent) exitSessions = 0L; // 마트는 있는데 이 상품 행이 없다 = 이탈 0
    else exitSessions = null; // 마트 자체가 없다 = 모른다
    Map<String, Object> out = new LinkedHashMap<>();
    out.put("exit_content_kind_top", topKind);
    out.put("exit_sessions", exitSessions);
    out.put("variant_select_per_session", variants);
    out.put("quick_look_open_detail_rate", quickLook);
    return out;
  }

  /* ------------------------------------------------------------------ E3 content */

  public Map<String, Object> content(String seller, String brand, String from, String to, String actor) {
    Read read = open(seller, brand, from, to, actor);
    Query q = read.q;

    List<Map<String, Object>> rows = read.required(
      "content_daily_kpi",
      () ->
        many(
          "select content_kind,coalesce(sum(section_view_count),0) section_view_count," +
            "coalesce(sum(section_view_sessions),0) section_view_sessions," +
            "coalesce(sum(dwell_ms_sum),0) dwell_ms_sum," +
            "coalesce(sum(accordion_expand_count),0) accordion_expand_count," +
            "coalesce(sum(text_selection_count),0) text_selection_count," +
            "coalesce(sum(text_copy_count),0) text_copy_count," +
            "coalesce(sum(matched_ingredient_count),0) matched_ingredient_count," +
            "min(mart_processed_at) mart_processed_at " +
            "from dw.content_daily_kpi where " + q.where("event_date_kst") + " group by content_kind",
          q.args()
        )
    );
    Object processedAt = rows.stream().map(r -> r.get("mart_processed_at")).filter(x -> x != null).findFirst().orElse(null);

    // `product_view_sessions` 는 **상품 단위** 값이라 content_kind·section_id 마다 같은 값이 반복된다.
    // 그 축으로 더하면 같은 세션을 콘텐츠 종류 수만큼 센다 (계약 E3 · dw-schema §4.4). 상품 grain 으로 되돌린 뒤 합산한다.
    long viewSessions = read.required(
      "content_daily_kpi",
      () ->
        longOf(
          one(
            "select coalesce(sum(pvs),0) product_view_sessions from (" +
              "select max(product_view_sessions) pvs from dw.content_daily_kpi where " + q.where("event_date_kst") +
              " group by event_date_kst,product_id," + EXECUTION_AXES + ") t",
            q.args()
          ).get("product_view_sessions")
        )
    );

    Map<String, Map<String, Object>> conversions = read.optional(
      "content_conversion_daily",
      () ->
        indexed(
          many(
            "select content_kind,coalesce(sum(viewed_sessions),0) viewed_sessions," +
              "coalesce(sum(viewed_cart_sessions),0) viewed_cart_sessions," +
              ratio("viewed_cart_sessions", "viewed_sessions", "viewed_cart_rate") +
              " from dw.content_conversion_daily where " + q.where("event_date_kst") + " group by content_kind",
            q.args()
          ),
          "content_kind"
        )
    );

    // 화면은 이 블록을 조건 없이 파고든다(`ct.brand.product_view_sessions`). null 을 보내면 대시보드가 멈추므로
    // 브랜드 마트가 없거나 행이 없으면 0 으로 채운다 — 값이 0 이면 cart_lift 가 알아서 null 이 된다.
    Map<String, Object> base = read.optional("brand_daily_kpi", () -> brandBase(q));
    if (base == null) base = emptyBrandBase();
    Double brandCartRate = doubleOrNull(base.get("view_to_cart_rate"));

    for (Map<String, Object> row : rows) {
      row.remove("mart_processed_at");
      row.put("product_view_sessions", viewSessions);
      row.put("avg_dwell_ms_per_session", divide(row.get("dwell_ms_sum"), viewSessions));
      row.put("view_rate", divide(row.get("section_view_sessions"), viewSessions));
      row.put(
        "conversion",
        conversion(conversions == null ? null : conversions.get(String.valueOf(row.get("content_kind"))), brandCartRate)
      );
    }

    List<Map<String, Object>> behaviors = read.optional("behavior_conversion_daily", () -> behaviors(q));

    Map<String, Object> body = new LinkedHashMap<>();
    body.put("by_content_kind", rows);
    body.put("brand", base);
    body.put("behaviors", behaviors);
    return read.envelope(
      List.of("content_daily_kpi", "content_conversion_daily", "behavior_conversion_daily", "brand_daily_kpi"),
      !rows.isEmpty(),
      processedAt,
      body
    );
  }

  /**
   * `cart_lift` 는 마트에 없다 — 서버가 나눈다 (계약 E3).
   * `cart_lift = viewed_cart_rate / brand.view_to_cart_rate`. 어느 쪽 분모든 0 이면 `null` 이다.
   */
  private Map<String, Object> conversion(Map<String, Object> row, Double brandCartRate) {
    if (row == null) return null;
    Double viewedCartRate = doubleOrNull(row.get("viewed_cart_rate"));
    Map<String, Object> out = new LinkedHashMap<>();
    out.put("viewed_sessions", longOf(row.get("viewed_sessions")));
    out.put("viewed_cart_sessions", longOf(row.get("viewed_cart_sessions")));
    out.put("viewed_cart_rate", viewedCartRate);
    boolean divisible = viewedCartRate != null && brandCartRate != null && brandCartRate != 0;
    out.put("cart_lift", divisible ? viewedCartRate / brandCartRate : null);
    return out;
  }

  /**
   * 행동 대조. **0건이어도 행이 온다** — 마트가 모집단 × Event 4종을 교차해 만들기 때문이다 (dw-schema §4.20).
   *
   * 이름을 둘 다 싣는다: 계약 0.3 의 `done_cart_rate`·`not_done_cart_rate` 와, 배포본 프론트가 읽는
   * `cart_rate_with`·`cart_rate_without`. 프론트 두 판본이 같은 응답으로 돌아야 배포 순서에 묶이지 않는다.
   */
  private List<Map<String, Object>> behaviors(Query q) {
    List<Map<String, Object>> rows = many(
      "select event_name,coalesce(sum(done_sessions),0) done_sessions," +
        "coalesce(sum(not_done_sessions),0) not_done_sessions," +
        ratio("done_cart_sessions", "done_sessions", "done_cart_rate") + "," +
        ratio("not_done_cart_sessions", "not_done_sessions", "not_done_cart_rate") +
        " from dw.behavior_conversion_daily where " + q.where("event_date_kst") + " group by event_name",
      q.args()
    );
    List<Map<String, Object>> out = new ArrayList<>();
    for (Map<String, Object> row : rows) {
      Map<String, Object> item = new LinkedHashMap<>();
      item.put("event", row.get("event_name"));
      item.put("done_sessions", longOf(row.get("done_sessions")));
      item.put("not_done_sessions", longOf(row.get("not_done_sessions")));
      item.put("done_cart_rate", doubleOrNull(row.get("done_cart_rate")));
      item.put("not_done_cart_rate", doubleOrNull(row.get("not_done_cart_rate")));
      item.put("cart_rate_with", doubleOrNull(row.get("done_cart_rate")));
      item.put("cart_rate_without", doubleOrNull(row.get("not_done_cart_rate")));
      out.add(item);
    }
    return out;
  }

  /* ------------------------------------------------------------------ E4 segments */

  public Map<String, Object> segments(String seller, String brand, String from, String to, String actor) {
    Read read = open(seller, brand, from, to, actor);
    Query q = read.q;

    List<Map<String, Object>> rows = read.required(
      "persona_segment_daily_kpi",
      () ->
        many(
          // segment_user_count 합은 하루 단위로 센 고객 수를 더한 값이다 (기간 고유 수 아님). 화면은 session_count 를 방문 수로 쓴다.
          "select segment_type,segment_value,coalesce(sum(segment_user_count),0) segment_user_count," +
            "coalesce(sum(session_count),0) session_count," +
            "coalesce(sum(product_view_sessions),0) product_view_sessions," +
            "coalesce(sum(detail_view_sessions),0) detail_view_sessions," +
            "coalesce(sum(add_to_cart_sessions),0) add_to_cart_sessions," +
            ratio("add_to_cart_sessions", "detail_view_sessions", "view_to_cart_rate") + "," +
            // 일별 평균을 다시 평균내지 않는다 (계약 §1-3). 세션 수로 가중한 합산 평균이다.
            "case when sum(session_count)=0 then null else " +
            "sum(avg_interest_score*session_count)/sum(session_count) end avg_interest_score," +
            "min(mart_processed_at) mart_processed_at " +
            "from dw.persona_segment_daily_kpi where " + q.where("event_date_kst") +
            " group by segment_type,segment_value",
          q.args()
        )
    );
    Object processedAt = rows.stream().map(r -> r.get("mart_processed_at")).filter(x -> x != null).findFirst().orElse(null);
    for (Map<String, Object> row : rows) row.remove("mart_processed_at");

    // 히트맵은 교차 축(`skin_type_x_skin_tone`) 행을 `|` 로 가른 것이다. 단일 축을 곱해 만들 수 없다.
    List<Map<String, Object>> grid = rows
      .stream()
      .filter(row -> "skin_type_x_skin_tone".equals(row.get("segment_type")))
      .map(DashboardMartService::gridCell)
      .filter(cell -> cell != null)
      .toList();

    List<Map<String, Object>> topContent = read.optional("segment_content_daily", () -> topContent(q));

    List<Map<String, Object>> priceBands = read.optional("brand_price_band_daily_kpi", () -> priceBands(q));
    List<Map<String, Object>> segmentPriceGrid = read.optional("segment_price_band_daily_kpi", () -> segmentPriceGrid(q));
    CohortResult cohort = read.optional("brand_cohort_dim", () -> cohort(read, q));
    Object priceProcessedAt = processedAt(priceBands);
    Object segmentPriceProcessedAt = processedAt(segmentPriceGrid);
    stripProcessedAt(priceBands);
    stripProcessedAt(segmentPriceGrid);

    Map<String, Object> body = new LinkedHashMap<>();
    body.put("by_segment", rows);
    body.put("grid", grid.isEmpty() ? null : grid);
    body.put("top_content", topContent);
    // `review_filter_apply(same_skin_type)` 를 가를 축이 마트에 없다. `behavior_conversion_daily` 는 Event 이름까지만
    // 나누고 필터 값은 싣지 않는다 (dw-schema §4.20). 값을 지어내지 않고 비운다 — 화면은 이 칸만 모의로 남는다.
    body.put("same_skin_filter_rate", null);
    body.put("price_bands", priceBands);
    body.put("segment_price_grid", segmentPriceGrid);
    body.put("cohort", cohort == null ? null : cohort.body());
    return read.envelope(
      List.of(
        "persona_segment_daily_kpi",
        "segment_content_daily",
        "brand_price_band_daily_kpi",
        "segment_price_band_daily_kpi",
        "brand_cohort_dim",
        "commons_cohort_weekly"
      ),
      !rows.isEmpty(),
      oldest(processedAt, priceProcessedAt, segmentPriceProcessedAt, cohort == null ? null : cohort.processedAt()),
      body
    );
  }

  private static Object processedAt(List<Map<String, Object>> rows) {
    if (rows == null) return null;
    Object result = null;
    for (Map<String, Object> row : rows) result = oldest(result, row.get("mart_processed_at"));
    return result;
  }

  private static void stripProcessedAt(List<Map<String, Object>> rows) {
    if (rows == null) return;
    for (Map<String, Object> row : rows) row.remove("mart_processed_at");
  }

  private static Object oldest(Object... values) {
    Object result = null;
    for (Object value : values) {
      if (value == null) continue;
      if (result == null) {
        result = value;
      } else if (value instanceof Timestamp next && result instanceof Timestamp current && next.before(current)) {
        result = value;
      }
    }
    return result;
  }

  /** 브랜드 × 가격대. 가격 축을 제거하지 않고 기간 합산한 뒤 비율을 다시 계산한다. */
  private List<Map<String, Object>> priceBands(Query q) {
    List<Map<String, Object>> rows = many(
      "select price_bin,currency," +
        "coalesce(sum(session_count),0) session_count," +
        "coalesce(sum(product_count),0) product_count," +
        "coalesce(sum(impression_sessions),0) impression_sessions," +
        "coalesce(sum(quick_look_sessions),0) quick_look_sessions," +
        "coalesce(sum(product_view_sessions),0) product_view_sessions," +
        "coalesce(sum(detail_view_sessions),0) detail_view_sessions," +
        "coalesce(sum(add_to_cart_sessions),0) add_to_cart_sessions," +
        "coalesce(sum(purchase_sessions),0) purchase_sessions," +
        ratio("detail_view_sessions", "impression_sessions", "detail_entry_rate") + "," +
        ratio("add_to_cart_sessions", "detail_view_sessions", "view_to_cart_rate") + "," +
        ratio("purchase_sessions", "detail_view_sessions", "view_to_purchase_rate") + "," +
        "min(mart_processed_at) mart_processed_at " +
        "from dw.brand_price_band_daily_kpi where " + q.where("event_date_kst") +
        " group by price_bin,currency",
      q.args()
    );
    return rows;
  }

  /** 고객군 × 가격대. by_segment와 다른 원본 축을 그대로 유지한다. */
  private List<Map<String, Object>> segmentPriceGrid(Query q) {
    List<Map<String, Object>> rows = many(
      "select segment_type,segment_value,price_bin,currency," +
        // 하루 단위 고객 수의 합이다. 기간 고유 수가 아니다.
        "coalesce(sum(segment_user_count),0) segment_user_count," +
        "coalesce(sum(session_count),0) session_count," +
        "coalesce(sum(product_count),0) product_count," +
        "coalesce(sum(product_view_sessions),0) product_view_sessions," +
        "coalesce(sum(detail_view_sessions),0) detail_view_sessions," +
        "coalesce(sum(add_to_cart_sessions),0) add_to_cart_sessions," +
        "coalesce(sum(purchase_sessions),0) purchase_sessions," +
        ratio("add_to_cart_sessions", "detail_view_sessions", "view_to_cart_rate") + "," +
        ratio("purchase_sessions", "detail_view_sessions", "view_to_purchase_rate") + "," +
        "min(mart_processed_at) mart_processed_at " +
        "from dw.segment_price_band_daily_kpi where " + q.where("event_date_kst") +
        " group by segment_type,segment_value,price_bin,currency",
      q.args()
    );
    return rows;
  }

  /**
   * B층 코호트. 먼저 브랜드의 cohort_key를 찾고, 그 키의 최신 주간 스냅샷을 읽는다.
   * commons_cohort_weekly에는 brand_id를 절대 넣지 않는다.
   */
  private CohortResult cohort(Read read, Query q) {
    List<Map<String, Object>> dimensions = many(
      "select cohort_key,product_count_band,dominant_price_bin,mart_processed_at " +
        "from dw.brand_cohort_dim where brand_id=?",
      q.brand()
    );
    if (dimensions.isEmpty() || dimensions.getFirst().get("cohort_key") == null) return null;

    Map<String, Object> dim = dimensions.getFirst();
    // Unlike additive Marts, cohort percentiles have a separately materialized
    // actor_type='all' row. Never combine execution-axis percentile rows.
    String actorClause = " and actor_type=?";
    // snapshot_week_kst는 KST 월요일이다. from이 주중이어도 그 주의 스냅샷을 포함한다.
    LocalDate snapshotFrom = q.from().minusDays(6);
    Object[] cohortArgs = new Object[] { dim.get("cohort_key"), Date.valueOf(snapshotFrom), Date.valueOf(q.to()), q.actor() };
    String cohortWhere = "cohort_key=? and snapshot_week_kst between ? and ?" + actorClause;
    List<Map<String, Object>> rows = many(
        "select metric_name,snapshot_week_kst,window_start_date,window_end_date,brand_count," +
        "is_suppressed,is_sample_sufficient,is_dominated,p25,p50,p75,mart_processed_at " +
        "from dw.commons_cohort_weekly where " + cohortWhere +
        " and snapshot_week_kst=(select max(snapshot_week_kst) from dw.commons_cohort_weekly where " + cohortWhere + ")" +
        " order by metric_name,mart_processed_at desc,source,generator_type,scenario_id,simulation_run_id",
      concat(cohortArgs, cohortArgs)
    );
    if (rows.isEmpty()) return null;

    Map<String, List<Map<String, Object>>> groupedMetrics = new LinkedHashMap<>();
    for (Map<String, Object> row : rows) {
      groupedMetrics.computeIfAbsent(String.valueOf(row.get("metric_name")), ignored -> new ArrayList<>()).add(row);
    }
    Map<String, Map<String, Object>> metricsByName = new LinkedHashMap<>();
    for (Map.Entry<String, List<Map<String, Object>>> entry : groupedMetrics.entrySet()) {
      List<Map<String, Object>> metricRows = entry.getValue();
      Map<String, Object> metricRow = metricRows.getFirst();
      if (q.actor().equals("all") && metricRows.size() > 1) {
        // p25/p50/p75 are already percentiles, so execution-axis rows cannot be
        // combined by summing or brand-count weighted averaging. Without the
        // underlying brand-level values, exposing a fabricated benchmark is worse
        // than leaving the comparison unavailable.
        metricRow = new LinkedHashMap<>(metricRow);
        metricRow.put("p25", null);
        metricRow.put("p50", null);
        metricRow.put("p75", null);
      }
      metricsByName.put(entry.getKey(), metricRow);
    }
    Map<String, Object> first = rows.getFirst();
    LocalDate windowStart = toLocalDate(first.get("window_start_date"));
    LocalDate windowEnd = toLocalDate(first.get("window_end_date"));
    Query window = new Query(q.brand(), windowStart, windowEnd, q.actor());
    Map<String, Object> mine = brandPeriodSqlRow(window);

    List<Map<String, Object>> metrics = new ArrayList<>();
    for (Map<String, Object> row : metricsByName.values()) {
      boolean suppressed = boolOf(row.get("is_suppressed"));
      Double p25 = suppressed ? null : doubleOrNull(row.get("p25"));
      Double p50 = suppressed ? null : doubleOrNull(row.get("p50"));
      Double p75 = suppressed ? null : doubleOrNull(row.get("p75"));
      Double myValue = myValue(row.get("metric_name"), mine);
      Map<String, Object> metric = new LinkedHashMap<>();
      metric.put("metric_name", row.get("metric_name"));
      metric.put("p25", p25);
      metric.put("p50", p50);
      metric.put("p75", p75);
      metric.put("my_value", myValue);
      metric.put("my_position", position(myValue, p25, p50, p75));
      metrics.add(metric);
    }

    Map<String, Object> body = new LinkedHashMap<>();
    body.put("cohort_key", dim.get("cohort_key"));
    body.put("product_count_band", dim.get("product_count_band"));
    body.put("dominant_price_bin", dim.get("dominant_price_bin"));
    body.put("snapshot_week_kst", dateText(first.get("snapshot_week_kst")));
    body.put("window_start_date", dateText(first.get("window_start_date")));
    body.put("window_end_date", dateText(first.get("window_end_date")));
    body.put("brand_count", longOf(first.get("brand_count")));
    body.put("is_suppressed", boolOf(first.get("is_suppressed")));
    body.put("is_sample_sufficient", boolOf(first.get("is_sample_sufficient")));
    body.put("is_dominated", boolOf(first.get("is_dominated")));
    body.put("metrics", metrics);

    Object processed = dimensions.getFirst().get("mart_processed_at");
    for (Map<String, Object> row : rows) processed = oldest(processed, row.get("mart_processed_at"));
    return new CohortResult(body, processed);
  }

  private Map<String, Object> brandPeriodSqlRow(Query q) {
    return one(brandPeriodSql(q), q.args());
  }

  private static Double myValue(Object metric, Map<String, Object> mine) {
    if (longOf(mine.get("row_count")) == 0) return null;
    return switch (String.valueOf(metric)) {
      case "detail_entry_rate" -> doubleOrNull(mine.get("detail_entry_rate"));
      case "view_to_cart_rate" -> doubleOrNull(mine.get("view_to_cart_rate"));
      case "information_view_rate" -> doubleOrNull(mine.get("information_view_rate"));
      default -> null;
    };
  }

  private static String position(Double value, Double p25, Double p50, Double p75) {
    if (value == null || p25 == null || p50 == null || p75 == null) return null;
    if (value < p25) return "below_p25";
    if (value < p50) return "p25_p50";
    if (value < p75) return "p50_p75";
    return "above_p75";
  }

  /**
   * 고객군별로 가장 오래 본 콘텐츠. `dwell_share` 의 분모(`segment_dwell_ms_sum`)는 **피부 타입 단위** 값이라
   * content_kind 마다 반복된다 — 그대로 더하면 분모가 종류 수만큼 부푼다. 타입 grain 으로 되돌린 뒤 나눈다.
   */
  private List<Map<String, Object>> topContent(Query q) {
    List<Map<String, Object>> rows = many(
      "select skin_type,content_kind,coalesce(sum(dwell_ms_sum),0) dwell_ms_sum " +
        "from dw.segment_content_daily where " + q.where("event_date_kst") + " group by skin_type,content_kind",
      q.args()
    );
    Map<String, Long> totals = new LinkedHashMap<>();
    for (Map<String, Object> row : many(
      "select skin_type,coalesce(sum(sd),0) segment_dwell_ms_sum from (" +
        "select skin_type,max(segment_dwell_ms_sum) sd from dw.segment_content_daily where " +
        q.where("event_date_kst") + " group by event_date_kst,skin_type," + EXECUTION_AXES +
        ") t group by skin_type",
      q.args()
    )) totals.put(String.valueOf(row.get("skin_type")), longOf(row.get("segment_dwell_ms_sum")));

    List<Map<String, Object>> out = new ArrayList<>();
    for (Map<String, Object> row : rows) {
      Long total = totals.get(String.valueOf(row.get("skin_type")));
      Map<String, Object> item = new LinkedHashMap<>();
      item.put("skin_type", row.get("skin_type"));
      item.put("content_kind", row.get("content_kind"));
      item.put("dwell_ms_sum", longOf(row.get("dwell_ms_sum")));
      item.put("dwell_share", total == null || total == 0 ? null : longOf(row.get("dwell_ms_sum")) / (double) total);
      out.add(item);
    }
    return out;
  }

  /* ------------------------------------------------------------------ E5 ingredients */

  public Map<String, Object> ingredients(String seller, String brand, String from, String to, String actor) {
    Read read = open(seller, brand, from, to, actor);
    Query q = read.q;

    // 이 마트에는 brand 축이 없다 — 플랫폼 전체 관심이다 (계약 E5).
    // 주(KST 월요일) 단위라 `from` 이 주 중간이면 그 주의 월요일이 범위 밖으로 떨어진다. 걸치는 주를 포함한다.
    Object[] args = q.weekArgs();
    String where = q.whereWeek();

    List<Map<String, Object>> rows = read.required(
      "ingredient_weekly_interest",
      () ->
        many(
          "select ingredient_id,max(ingredient) ingredient,max(label_ko) label_ko,max(vocab_version) vocab_version," +
            "coalesce(sum(ingredient_interest_score),0) ingredient_interest_score," +
            "coalesce(sum(direct_match_score),0) direct_match_score," +
            "coalesce(sum(product_attributed_score),0) product_attributed_score," +
            "coalesce(sum(contributing_event_count),0) contributing_event_count," +
            "min(mart_processed_at) mart_processed_at " +
            "from dw.ingredient_weekly_interest where " + where + " group by ingredient_id",
          args
        )
    );
    Object processedAt = rows.stream().map(r -> r.get("mart_processed_at")).filter(x -> x != null).findFirst().orElse(null);

    // share 는 합산 후 다시 계산한다 (계약 §1-3). 관심 점수는 음수일 수 있어(dw-schema §6.8) 총합이 0 일 수 있다.
    double total = rows.stream().mapToDouble(r -> doubleOf(r.get("ingredient_interest_score"))).sum();
    for (Map<String, Object> row : rows) {
      row.remove("mart_processed_at");
      row.put("ingredient_interest_share", total == 0 ? null : doubleOf(row.get("ingredient_interest_score")) / total);
    }

    List<Object> weeks = read
      .required(
        "ingredient_weekly_interest",
        () -> many("select distinct interest_week_kst from dw.ingredient_weekly_interest where " + where + " order by interest_week_kst", args)
      )
      .stream()
      .map(row -> (Object) dateText(row.get("interest_week_kst")))
      .toList();

    Map<String, Object> body = new LinkedHashMap<>();
    body.put("weeks", weeks);
    body.put("by_ingredient", rows);
    return read.envelope(List.of("ingredient_weekly_interest"), !rows.isEmpty(), processedAt, body);
  }

  /* ------------------------------------------------------------------ E6 friction */

  public Map<String, Object> friction(String seller, String brand, String from, String to, String actor) {
    Read read = open(seller, brand, from, to, actor);
    Query q = read.q;

    List<Map<String, Object>> locations = read.required(
      "friction_daily",
      () ->
        many(
          "select section_id,event_name,coalesce(sum(event_count),0) event_count," +
            "coalesce(sum(friction_sessions),0) session_count,min(mart_processed_at) mart_processed_at " +
            "from dw.friction_daily where " + q.where("event_date_kst") + " group by section_id,event_name",
          q.args()
        )
    );
    Object processedAt = locations.stream().map(r -> r.get("mart_processed_at")).filter(x -> x != null).findFirst().orElse(null);
    for (Map<String, Object> row : locations) row.remove("mart_processed_at");

    // 세 Event 는 0 이어도 키를 지우지 않는다. 화면이 "이 로그에는 없다" 를 적어야 해서,
    // 0 인 것과 집계하지 않는 것이 구분돼야 한다 (계약 E6).
    Map<String, Object> counts = new LinkedHashMap<>();
    counts.put("rage_click", 0L);
    counts.put("dead_click", 0L);
    counts.put("scroll_backtrack", 0L);
    for (Map<String, Object> row : locations) {
      String event = String.valueOf(row.get("event_name"));
      if (counts.containsKey(event)) counts.put(event, longOf(counts.get(event)) + longOf(row.get("event_count")));
    }

    // 분모는 상세를 연 세션 전체다. exit_summary 가 없는 세션은 "빨리 나가지 않았다" 가 아니라 "기록이 없다".
    Map<String, Object> exit = read.optional(
      "exit_daily",
      () ->
        one(
          "select " + ratio("quick_exit_sessions", "detail_view_sessions", "quick_exit_rate") +
            ",count(*) row_count from dw.exit_daily where " + q.where("event_date_kst"),
          q.args()
        )
    );

    List<Map<String, Object>> entry = read.optional(
      "entry_source_daily",
      () ->
        many(
          "select entry_source,coalesce(sum(product_view_sessions),0) product_view_sessions," +
            "coalesce(sum(detail_view_sessions),0) detail_view_sessions," +
            "coalesce(sum(add_to_cart_sessions),0) add_to_cart_sessions," +
            ratio("add_to_cart_sessions", "detail_view_sessions", "view_to_cart_rate") +
            " from dw.entry_source_daily where " + q.where("event_date_kst") + " group by entry_source",
          q.args()
        )
    );

    List<Map<String, Object>> volumes = read.optional(
      "event_daily",
      () ->
        many(
          "select event_name,coalesce(sum(event_count),0) event_count " +
            "from dw.event_daily where " + q.where("event_date_kst") + " group by event_name order by 2 desc",
          q.args()
        )
    );

    Map<String, Object> body = new LinkedHashMap<>();
    body.put("by_location", locations);
    body.put("counts", counts);
    body.put("quick_exit_rate", exit == null || longOf(exit.get("row_count")) == 0 ? null : doubleOrNull(exit.get("quick_exit_rate")));
    body.put("entry_source", entry);
    body.put("event_volumes", volumes);
    return read.envelope(
      List.of("friction_daily", "exit_daily", "entry_source_daily", "event_daily"),
      !locations.isEmpty(),
      processedAt,
      body
    );
  }

  /* ------------------------------------------------------------------ E7 purchase */

  public Map<String, Object> purchase(String seller, String brand, String from, String to, String actor) {
    Read read = open(seller, brand, from, to, actor);
    Query q = read.q;

    // 재구매 두 마트는 창(window_days)이 들어 있는 **스냅샷** 이라 기간 합산하지 않는다. 최신 스냅샷만 읽는다.
    Map<String, Object> brandRow = read.required("brand_repurchase_daily", () -> brandRepurchase(q));
    List<Map<String, Object>> products = read.optional("product_repurchase_daily", () -> productRepurchase(q));
    List<Map<String, Object>> reasons = read.optional("purchase_reason_daily", () -> reasons(q));

    Object processedAt = brandRow == null ? null : brandRow.remove("mart_processed_at");
    boolean any = brandRow != null || (products != null && !products.isEmpty()) || (reasons != null && !reasons.isEmpty());

    Map<String, Object> body = new LinkedHashMap<>();
    body.put("brand", brandRow);
    body.put("products", products == null ? List.of() : products);
    body.put("reasons", reasons == null ? List.of() : reasons);
    return read.envelope(
      List.of("brand_repurchase_daily", "product_repurchase_daily", "purchase_reason_daily"),
      any,
      processedAt,
      body
    );
  }

  private Map<String, Object> brandRepurchase(Query q) {
    Map<String, Object> row = one(
      "select coalesce(sum(buyer_count),0) buyer_count,coalesce(sum(repeat_buyer_count),0) repeat_buyer_count," +
        "coalesce(sum(purchase_order_count),0) purchase_order_count," +
        "coalesce(sum(declared_restock_order_count),0) declared_restock_order_count," +
        // 중앙값은 합산할 수 없다. 다만 실행 축이 여러 개여도 각 축의 값이
        // 동일하면 같은 모집단을 중복 투영한 것이므로 그 값을 유지한다.
        // 축별 중앙값이 실제로 다를 때만 null을 반환해 잘못된 재집계를 막는다.
        "case when count(median_days_between_purchases)=0 then null " +
          "when min(median_days_between_purchases)=max(median_days_between_purchases) " +
          "then max(median_days_between_purchases) else null end median_days_between_purchases," +
        "max(window_days) window_days,min(window_start_date) window_start_date,max(window_end_date) window_end_date," +
        "min(mart_processed_at) mart_processed_at,count(*) row_count " +
        "from dw.brand_repurchase_daily where " + q.where("snapshot_date_kst") +
        " and snapshot_date_kst=(select max(snapshot_date_kst) from dw.brand_repurchase_daily where " +
        q.where("snapshot_date_kst") + ")",
      concat(q.args(), q.args())
    );
    if (longOf(row.remove("row_count")) == 0) return null;
    row.put("window_start_date", dateText(row.get("window_start_date")));
    row.put("window_end_date", dateText(row.get("window_end_date")));
    row.put("repurchase_rate", divide(row.get("repeat_buyer_count"), row.get("buyer_count")));
    return row;
  }

  private List<Map<String, Object>> productRepurchase(Query q) {
    List<Map<String, Object>> rows = many(
      "select product_id,coalesce(sum(buyer_count),0) buyer_count," +
        "coalesce(sum(repeat_buyer_count),0) repeat_buyer_count," +
        "coalesce(sum(purchase_order_count),0) purchase_order_count," +
        ratio("repeat_buyer_count", "buyer_count", "repurchase_rate") +
        " from dw.product_repurchase_daily where " + q.where("snapshot_date_kst") +
        " and snapshot_date_kst=(select max(snapshot_date_kst) from dw.product_repurchase_daily where " +
        q.where("snapshot_date_kst") + ") group by product_id",
      concat(q.args(), q.args())
    );
    return rows;
  }

  /**
   * 구매 사유. `reason` 이 NULL 인 행은 "설문을 건너뛴 주문" 이라 사유가 아니다 — 비중의 분모에서 뺀다
   * (계약 E7 "reason NULL 은 skipped_order_count 로만"). 행 자체는 남겨 건너뛴 양을 볼 수 있게 한다.
   */
  private List<Map<String, Object>> reasons(Query q) {
    List<Map<String, Object>> rows = many(
      "select reason,coalesce(sum(order_count),0) order_count," +
        "coalesce(sum(primary_order_count),0) primary_order_count," +
        "coalesce(sum(skipped_order_count),0) skipped_order_count " +
        "from dw.purchase_reason_daily where " + q.where("event_date_kst") + " group by reason",
      q.args()
    );
    double named = rows.stream().filter(r -> r.get("reason") != null).mapToDouble(r -> doubleOf(r.get("order_count"))).sum();
    for (Map<String, Object> row : rows) {
      boolean counted = row.get("reason") != null && named != 0;
      row.put("reason_share", counted ? doubleOf(row.get("order_count")) / named : null);
    }
    return rows;
  }

  /* ------------------------------------------------------------------ 공통 */

  private Read open(String seller, String brand, String from, String to, String actor) {
    owns(seller, brand);
    return new Read(Query.parse(brand, from, to, actor));
  }

  private void owns(String seller, String brand) {
    Integer count = shopJdbc.queryForObject(
      "select count(*) from brand where brand_id=? and seller_account_id=?",
      Integer.class,
      brand,
      seller
    );
    if (count == null || count == 0) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "brand access denied");
  }

  /**
   * 한 번의 요청. 어떤 보조 마트가 빠졌는지를 모아 `coverage` 를 정한다.
   *
   * `optional` 은 **테이블이 없을 때만** 삼킨다. DW 연결 자체가 없으면 블록만 비워서 될 일이 아니라 그대로 올려 보낸다.
   */
  private final class Read {

    private final Query q;
    private final Set<String> missing = new LinkedHashSet<>();

    private Read(Query q) {
      this.q = q;
    }

    <T> T required(String mart, Supplier<T> body) {
      return body.get();
    }

    <T> T optional(String mart, Supplier<T> body) {
      try {
        return body.get();
      } catch (DashboardMartUnavailableException exception) {
        if (NO_CONNECTION.equals(exception.mart())) throw exception;
        missing.add(exception.mart());
        return null;
      }
    }

    Map<String, Object> envelope(List<String> marts, boolean hasRows, Object processedAt, Map<String, Object> body) {
      Map<String, Object> source = new LinkedHashMap<>();
      source.put("marts", marts);
      source.put("mart_processed_at", timestampText(processedAt));
      source.put("coverage", hasRows ? (missing.isEmpty() ? "full" : "partial") : "none");
      if (!missing.isEmpty()) source.put("missing_marts", List.copyOf(missing));

      Map<String, Object> out = new LinkedHashMap<>();
      out.put("brand_id", q.brand());
      out.put("range", Map.of("from", q.from().toString(), "to", q.to().toString(), "days", q.days()));
      out.put("actor_type", q.actor());
      out.put("source", source);
      out.putAll(body);
      return out;
    }
  }

  private Map<String, Object> one(String sql, Object... args) {
    try {
      return new LinkedHashMap<>(martJdbc.jdbc().queryForMap(sql, args));
    } catch (BadSqlGrammarException exception) {
      throw unavailable(exception);
    }
  }

  private List<Map<String, Object>> many(String sql, Object... args) {
    try {
      return martJdbc.jdbc().queryForList(sql, args).stream().<Map<String, Object>>map(LinkedHashMap::new).toList();
    } catch (BadSqlGrammarException exception) {
      throw unavailable(exception);
    }
  }

  private Map<String, Object> brandBase(Query q) {
    Map<String, Object> row = one(
      "select coalesce(sum(product_view_sessions),0) product_view_sessions," +
        "coalesce(sum(detail_view_sessions),0) detail_view_sessions," +
        "coalesce(sum(add_to_cart_sessions),0) add_to_cart_sessions," +
        ratio("add_to_cart_sessions", "detail_view_sessions", "view_to_cart_rate") +
        ",count(*) row_count from dw.brand_daily_kpi where " + q.where("event_date_kst"),
      q.args()
    );
    return longOf(row.remove("row_count")) == 0 ? null : row;
  }

  private static Map<String, Object> emptyBrandBase() {
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("product_view_sessions", 0L);
    row.put("detail_view_sessions", 0L);
    row.put("add_to_cart_sessions", 0L);
    row.put("view_to_cart_rate", null);
    return row;
  }

  private static Map<String, Object> nullIfNoRows(Map<String, Object> row) {
    if (longOf(row.remove("row_count")) == 0) return null;
    return row;
  }

  private DashboardMartUnavailableException unavailable(BadSqlGrammarException exception) {
    Matcher matcher = DW_TABLE.matcher(exception.getSql() == null ? "" : exception.getSql());
    return new DashboardMartUnavailableException(matcher.find() ? matcher.group(1) : "unknown");
  }

  /** 분모 0 이면 NULL. 마트가 비율을 비우는 규칙과 같다 (dw-schema §2.2) */
  private static String ratio(String numerator, String denominator, String alias) {
    String n = numerator.contains("(") ? numerator : "sum(" + numerator + ")";
    String d = denominator.contains("(") ? denominator : "sum(" + denominator + ")";
    return "case when " + d + "=0 then null else " + n + "/" + d + " end " + alias;
  }

  private static double doubleOf(Object value) {
    return value instanceof Number number ? number.doubleValue() : 0;
  }

  private static Double doubleOrNull(Object value) {
    return value instanceof Number number ? number.doubleValue() : null;
  }

  private static long longOf(Object value) {
    return value instanceof Number number ? number.longValue() : 0L;
  }

  private static boolean boolOf(Object value) {
    if (value instanceof Boolean bool) return bool;
    if (value instanceof Number number) return number.intValue() != 0;
    return "true".equalsIgnoreCase(String.valueOf(value));
  }

  private static LocalDate toLocalDate(Object value) {
    if (value instanceof Date date) return date.toLocalDate();
    if (value instanceof LocalDate date) return date;
    return LocalDate.parse(String.valueOf(value));
  }

  private static Double divide(Object numerator, Object denominator) {
    double d = doubleOf(denominator);
    return d == 0 ? null : doubleOf(numerator) / d;
  }

  private static Map<String, Map<String, Object>> indexed(List<Map<String, Object>> rows, String key) {
    Map<String, Map<String, Object>> out = new LinkedHashMap<>();
    for (Map<String, Object> row : rows) out.put(String.valueOf(row.get(key)), row);
    return out;
  }

  private static Map<String, Object> gridCell(Map<String, Object> row) {
    String[] parts = String.valueOf(row.get("segment_value")).split("\\|", 2);
    if (parts.length != 2) return null;
    Map<String, Object> cell = new LinkedHashMap<>();
    cell.put("skin_type", parts[0]);
    cell.put("skin_tone", parts[1]);
    for (String key : List.of("product_view_sessions", "detail_view_sessions", "add_to_cart_sessions", "view_to_cart_rate")) {
      cell.put(key, row.get(key));
    }
    return cell;
  }

  /** 날짜는 문자열로 보낸다. 직렬화 설정에 따라 숫자(epoch)가 되면 화면이 날짜를 잘라 쓰다가 깨진다 */
  private static String dateText(Object value) {
    if (value == null) return null;
    if (value instanceof Date date) return date.toLocalDate().toString();
    if (value instanceof LocalDate date) return date.toString();
    return String.valueOf(value);
  }

  /**
   * 마트 갱신 시각. projection 은 Spark 의 UTC timestamp 를 그대로 `DATETIME(3)` 에 넣으므로(DW_PROJECTION.md,
   * dw_projection_source.py 가 naive UTC 로 바꿔 쓴다) UTC 로 읽어 KST 로 적는다. UTC→KST 변환은 **여기 한 곳**에서만 한다 —
   * 화면(fmtProcessedAt)은 받은 `+09:00` 문자열의 벽시계 값을 그대로 풀어 쓸 뿐이다 (계약 §1-3).
   *
   * MySQL Connector/J 8 은 DATETIME 을 `getObject` 로 `LocalDateTime` 으로 준다 (H2 는 `Timestamp`). 예전에는 Timestamp 만
   * 바꿔서 실제 MySQL 에서는 UTC 벽시계가 오프셋 없이 나가 화면이 9시간 이른 시각을 KST 로 보였다.
   */
  static String timestampText(Object value) {
    if (value == null) return null;
    LocalDateTime utc;
    if (value instanceof Timestamp timestamp) utc = timestamp.toLocalDateTime();
    else if (value instanceof LocalDateTime local) utc = local;
    else return String.valueOf(value);
    return utc.atOffset(ZoneOffset.UTC).atZoneSameInstant(KST).toOffsetDateTime().toString();
  }

  private static Object[] concat(Object[] left, Object[] right) {
    Object[] out = new Object[left.length + right.length];
    System.arraycopy(left, 0, out, 0, left.length);
    System.arraycopy(right, 0, out, left.length, right.length);
    return out;
  }

  private record CohortResult(Map<String, Object> body, Object processedAt) {}

  /* ------------------------------------------------------------------ 요청 해석 */

  record Query(String brand, LocalDate from, LocalDate to, String actor) {
    static Query parse(String brand, String rawFrom, String rawTo, String rawActor) {
      String actor = rawActor == null || rawActor.isBlank() ? "all" : rawActor;
      if (LEGACY_USER_ACTOR.equals(actor)) actor = "user";
      if (!ACTOR_TYPES.contains(actor)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "bad_actor_type");
      LocalDate end;
      LocalDate start;
      try {
        end = rawTo == null || rawTo.isBlank() ? LocalDate.now(KST).minusDays(1) : LocalDate.parse(rawTo);
        start = rawFrom == null || rawFrom.isBlank() ? end.minusDays(DEFAULT_RANGE_DAYS - 1) : LocalDate.parse(rawFrom);
      } catch (RuntimeException exception) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "bad_range");
      }
      if (start.isAfter(end)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "bad_range");
      if (end.toEpochDay() - start.toEpochDay() + 1 > MAX_RANGE_DAYS) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "range_too_long");
      }
      return new Query(brand, start, end, actor);
    }

    String where(String dateColumn) {
      return "brand_id=? and " + dateColumn + " between ? and ?" + actorClause();
    }

    /** 브랜드 축이 없는 마트(ingredient_weekly_interest)용. 걸치는 주를 포함한다 */
    String whereWeek() {
      return "interest_week_kst between ? and ?" + actorClause();
    }

    Object[] args() {
      return actorClause().isEmpty()
        ? new Object[] { brand, Date.valueOf(from), Date.valueOf(to) }
        : new Object[] { brand, Date.valueOf(from), Date.valueOf(to), actor };
    }

    Object[] weekArgs() {
      LocalDate weekStart = from.minusDays(6);
      return actorClause().isEmpty()
        ? new Object[] { Date.valueOf(weekStart), Date.valueOf(to) }
        : new Object[] { Date.valueOf(weekStart), Date.valueOf(to), actor };
    }

    private String actorClause() {
      return "all".equals(actor) ? "" : " and actor_type=?";
    }

    int days() {
      return (int) (to.toEpochDay() - from.toEpochDay() + 1);
    }

    Query previous() {
      return new Query(brand, from.minusDays(days()), from.minusDays(1), actor);
    }
  }
}
