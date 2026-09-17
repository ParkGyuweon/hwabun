package com.cosmetic.shopbackend.dashboard;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Lazily opens the read-only connection to the DW projection database. */
@Component
public class DashboardMartJdbcProvider {
  private final String url;
  private final String username;
  private final String password;
  private volatile HikariDataSource dataSource;

  public DashboardMartJdbcProvider(
    @Value("${DASHBOARD_MART_MYSQL_URL:}") String url,
    @Value("${DW_MYSQL_USER:}") String username,
    @Value("${DW_MYSQL_PASSWORD:}") String password
  ) {
    this.url = url;
    this.username = username;
    this.password = password;
  }

  public JdbcTemplate jdbc() {
    if (url.isBlank() || username.isBlank() || password.isBlank()) {
      throw new DashboardMartUnavailableException("dw_connection");
    }
    HikariDataSource current = dataSource;
    if (current == null) {
      synchronized (this) {
        current = dataSource;
        if (current == null) {
          HikariConfig config = new HikariConfig();
          config.setJdbcUrl(url);
          config.setUsername(username);
          config.setPassword(password);
          config.setDriverClassName("com.mysql.cj.jdbc.Driver");
          config.setMaximumPoolSize(4);
          config.setReadOnly(true);
          config.setPoolName("dashboard-mart-read");
          try {
            dataSource = current = new HikariDataSource(config);
          } catch (RuntimeException exception) {
            throw new DashboardMartUnavailableException("dw_connection");
          }
        }
      }
    }
    return new JdbcTemplate(current);
  }

  @PreDestroy
  void close() {
    if (dataSource != null) dataSource.close();
  }
}
