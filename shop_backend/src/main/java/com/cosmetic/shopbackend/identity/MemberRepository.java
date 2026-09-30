package com.cosmetic.shopbackend.identity;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MemberRepository extends JpaRepository<Member, String> {
  Optional<Member> findByEmail(String email);

  /** JWT 필터가 회원 요청마다 부른다 — 엔티티 전체가 아니라 상태 한 칸만 PK 로 읽는다 */
  @Query("select m.status from Member m where m.id = :id")
  Optional<AccountStatus> findStatusById(@Param("id") String id);
}
