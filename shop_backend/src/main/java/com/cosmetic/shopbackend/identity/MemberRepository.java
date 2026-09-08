package com.cosmetic.shopbackend.identity;
import org.springframework.data.jpa.repository.JpaRepository; import java.util.Optional;
public interface MemberRepository extends JpaRepository<Member,String>{ Optional<Member> findByEmail(String email); }
