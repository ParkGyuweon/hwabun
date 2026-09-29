package com.cosmetic.shopbackend.identity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.cosmetic.shopbackend.commerce.ShopOrder;
import com.cosmetic.shopbackend.commerce.ShopOrderRepository;
import jakarta.persistence.EntityManager;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Optional;
import org.hibernate.SessionFactory;
import org.hibernate.cfg.Configuration;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.jpa.repository.support.JpaRepositoryFactory;

/**
 * 탈퇴가 새로 쓰는 저장소 질의 두 개(JPQL 상태 조회, 파생 exists 질의)가 실제 Hibernate 로 파싱·실행되는지.
 * 스프링 컨텍스트 없이 H2 위에 두 엔티티만 올린다 — 이 프로젝트 테스트는 컨텍스트를 띄우지 않는다.
 */
class WithdrawalRepositoryQueryTest {

  private SessionFactory factory;
  private EntityManager em;
  private MemberRepository members;
  private ShopOrderRepository orders;

  @BeforeEach
  void setUp() {
    factory = new Configuration()
      .addAnnotatedClass(Member.class)
      .addAnnotatedClass(ShopOrder.class)
      .setProperty("hibernate.connection.url", "jdbc:h2:mem:withdrawal;MODE=MySQL;DB_CLOSE_DELAY=-1")
      .setProperty("hibernate.hbm2ddl.auto", "create-drop")
      .buildSessionFactory();
    em = factory.createEntityManager();
    JpaRepositoryFactory repositories = new JpaRepositoryFactory(em);
    members = repositories.getRepository(MemberRepository.class);
    orders = repositories.getRepository(ShopOrderRepository.class);
  }

  @AfterEach
  void tearDown() {
    em.close();
    factory.close();
  }

  @Test
  void statusLookupAndInFlightOrderQueryWork() {
    Member m = new Member();
    m.setEmail("q@example.com");
    m.setNickname("q");
    m.setPasswordHash("x");
    em.getTransaction().begin();
    em.persist(m);
    ShopOrder order = new ShopOrder("o-1", m.getId(), "k-1", "h".repeat(64), BigDecimal.TEN);
    em.persist(order);
    em.getTransaction().commit();

    assertEquals(Optional.of(AccountStatus.ACTIVE), members.findStatusById(m.getId()));
    assertEquals(Optional.empty(), members.findStatusById("nobody"));

    LocalDateTime created = order.getCreatedAt();
    assertTrue(orders.existsByMemberIdAndStatusAndCreatedAtAfter(m.getId(), ShopOrder.Status.CREATED, created.minusMinutes(30)));
    assertFalse(orders.existsByMemberIdAndStatusAndCreatedAtAfter(m.getId(), ShopOrder.Status.CREATED, created.plusMinutes(1)));
    assertFalse(orders.existsByMemberIdAndStatusAndCreatedAtAfter(m.getId(), ShopOrder.Status.PAID, created.minusMinutes(30)));
    assertFalse(orders.existsByMemberIdAndStatusAndCreatedAtAfter("other", ShopOrder.Status.CREATED, created.minusMinutes(30)));
  }
}
