package com.cosmetic.shopbackend.dashboard;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

/** Smoke test against the local MySQL DW; opt in with RUN_DW_INTEGRATION=true. */
@EnabledIfEnvironmentVariable(named = "RUN_DW_INTEGRATION", matches = "true")
class DashboardMartDwIntegrationTest {
  private static final String BRAND = "6018";
  private static final String ACTOR = "web";
  private static final String SOURCE = "codex-test";
  private final JdbcTemplate shop = jdbc(
    env("SHOP_BACKEND_MYSQL_URL", "jdbc:mysql://localhost:13306/shop_backend"),
    env("SHOP_BACKEND_MYSQL_USER", "shop_backend"),
    env("SHOP_BACKEND_MYSQL_PASSWORD", "shop_backend_dev")
  );
  private final JdbcTemplate dwAdmin = jdbc(
    env("DASHBOARD_MART_MYSQL_URL", "jdbc:mysql://localhost:13306/dw"),
    env("DW_TEST_ADMIN_USER", "root"),
    env("DW_TEST_ADMIN_PASSWORD", "shop_backend_root_dev")
  );
  private final DashboardMartService service = new DashboardMartService(
    shop,
    new DashboardMartJdbcProvider(
      env("DASHBOARD_MART_MYSQL_URL", "jdbc:mysql://localhost:13306/dw"),
      env("DW_MYSQL_USER", "root"),
      env("DW_MYSQL_PASSWORD", "shop_backend_root_dev")
    )
  );

  @BeforeEach
  void insertMockMartRow() {
    dwAdmin.update(
      "insert into dw.brand_daily_kpi " +
        "(brand_id,event_date_kst,actor_type,source,generator_type,scenario_id,simulation_run_id," +
        "impression_sessions,click_sessions,quick_look_sessions,detail_view_sessions,product_view_sessions," +
        "information_view_sessions,add_to_cart_sessions,unique_user_count,product_count_viewed,mart_processed_at) " +
        "values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      BRAND, "2026-09-16", ACTOR, SOURCE, "manual", "codex", "run-1",
      100, 40, 20, 30, 50, 15, 10, 80, 5, "2026-09-17 01:00:00"
    );
  }

  @AfterEach
  void removeMockMartRow() {
    dwAdmin.update(
      "delete from dw.brand_daily_kpi where brand_id=? and actor_type=? and source=? and scenario_id=?",
      BRAND, ACTOR, SOURCE, "codex"
    );
  }

  @Test
  void readsMockRowThroughSeparateDwConnection() {
    Map<String, Object> response = service.overview("brand-admin-6018", BRAND, "2026-09-16", "2026-09-16", ACTOR);

    assertEquals(BRAND, response.get("brand_id"));
    assertEquals("full", ((Map<?, ?>) response.get("source")).get("coverage"));
    Map<?, ?> current = (Map<?, ?>) response.get("current");
    assertEquals(100L, ((Number) current.get("impression_sessions")).longValue());
    assertEquals(0.3D, ((Number) current.get("detail_entry_rate")).doubleValue(), 0.0001D);
    assertTrue(((Map<?, ?>) response.get("source")).get("mart_processed_at") != null);
  }

  private static JdbcTemplate jdbc(String url, String user, String password) {
    DriverManagerDataSource dataSource = new DriverManagerDataSource(url, user, password);
    dataSource.setDriverClassName("com.mysql.cj.jdbc.Driver");
    return new JdbcTemplate(dataSource);
  }

  private static String env(String name, String fallback) {
    String value = System.getenv(name);
    return value == null || value.isBlank() ? fallback : value;
  }
}
