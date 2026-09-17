package com.cosmetic.shopbackend.dashboard;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

/**
 * 테스트용 DW. `contracts/dw/schema.sql` 을 **그대로 읽어** H2(MySQL 호환 모드)에 올린다.
 *
 * 컬럼 목록을 테스트에 손으로 옮겨 적지 않는 것이 요점이다. 마트에 없는 컬럼을 조회 SQL 이 읽으면 테스트가
 * 실패해야 한다 — 손으로 옮긴 DDL 로는 그 실수가 그대로 통과한다.
 *
 * H2 가 못 받는 MySQL 문법만 걷어낸다. 컬럼 이름·타입·NULL 여부는 건드리지 않는다.
 * 하나 예외가 있다: NOT NULL 컬럼에 기본값을 붙인다. 마트 한 테이블이 컬럼 스무 개가 넘어 테스트마다 전부
 * 나열하면 무엇을 검증하는지가 안 보인다. 집계·분모를 보는 테스트라 이 완화는 검증 대상이 아니다.
 */
final class DwTestSchema {

  private DwTestSchema() {}

  /** 저장소 루트의 계약 DDL. 테스트는 shop_backend/ 에서 실행된다 */
  private static final Path SCHEMA = Path.of("..", "contracts", "dw", "schema.sql");

  static JdbcTemplate freshDatabase() {
    String name = "dwtest_" + UUID.randomUUID().toString().replace("-", "");
    DriverManagerDataSource dataSource = new DriverManagerDataSource(
      "jdbc:h2:mem:" + name + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;CASE_INSENSITIVE_IDENTIFIERS=TRUE;DB_CLOSE_DELAY=-1",
      "sa",
      "dw-test"
    );
    dataSource.setDriverClassName("org.h2.Driver");
    JdbcTemplate jdbc = new JdbcTemplate(dataSource);
    for (String statement : statements()) jdbc.execute(statement);
    // 브랜드 소유 확인은 쇼핑몰 DB 를 읽는다. 같은 H2 의 기본 스키마에 둔다.
    jdbc.execute("create table brand (brand_id varchar(64), seller_account_id varchar(64))");
    return jdbc;
  }

  static List<String> statements() {
    String raw;
    try {
      raw = Files.readString(SCHEMA, StandardCharsets.UTF_8);
    } catch (IOException exception) {
      throw new IllegalStateException("contracts/dw/schema.sql 을 읽지 못했다", exception);
    }
    StringBuilder withoutComments = new StringBuilder();
    for (String line : raw.split("\\R")) {
      if (line.stripLeading().startsWith("--")) continue;
      withoutComments.append(line).append('\n');
    }

    List<String> out = new ArrayList<>();
    for (String chunk : withoutComments.toString().split(";")) {
      String statement = chunk.strip();
      if (statement.isEmpty()) continue;
      if (statement.toUpperCase().startsWith("CREATE DATABASE")) {
        out.add("create schema if not exists dw");
        continue;
      }
      out.add(translate(statement));
    }
    return out;
  }

  private static String translate(String statement) {
    List<String> kept = new ArrayList<>();
    for (String line : statement.split("\\R")) {
      String trimmed = line.strip();
      // H2 는 CREATE TABLE 안의 보조 인덱스(KEY ...) 를 받지 않는다. 조회 결과에 영향이 없어 뺀다.
      if (trimmed.startsWith("KEY ")) continue;
      kept.add(line);
    }
    String body = String.join("\n", kept);
    body = body.replaceAll("(?i)\\)\\s*ENGINE=[^;]*$", ")");
    body = body.replaceAll("(?i)DATETIME\\(3\\)", "TIMESTAMP(3)");
    body = body.replaceAll("(?i)TINYINT\\(1\\)", "TINYINT");
    // KEY 줄을 빼면 그 앞줄의 쉼표가 닫는 괄호와 붙는다.
    body = body.replaceAll(",(\\s*)\\)", "$1)");
    return defaults(body);
  }

  /** NOT NULL 컬럼에 기본값을 붙인다. AUTO_INCREMENT 대리키는 건드리지 않는다 */
  private static String defaults(String body) {
    List<String> out = new ArrayList<>();
    for (String line : body.split("\\R")) {
      String trimmed = line.strip();
      if (trimmed.contains("AUTO_INCREMENT") || !trimmed.contains("NOT NULL") || trimmed.startsWith("PRIMARY KEY")) {
        out.add(line);
        continue;
      }
      String upper = trimmed.toUpperCase();
      String fill = null;
      if (upper.contains("BIGINT") || upper.contains("INT") || upper.contains("DOUBLE") || upper.contains("DECIMAL")) fill = "0";
      else if (upper.contains("VARCHAR")) fill = "''";
      else if (upper.contains("TIMESTAMP")) fill = "TIMESTAMP '2026-01-01 00:00:00'";
      else if (upper.contains("DATE")) fill = "DATE '2026-01-01'";
      out.add(fill == null ? line : line.replace("NOT NULL", "NOT NULL DEFAULT " + fill));
    }
    return String.join("\n", out);
  }
}
