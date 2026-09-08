package com.cosmetic.shopbackend.commerce; import org.springframework.data.jpa.repository.*; import java.util.*;
public interface CartRepository extends JpaRepository<Cart,String>{Optional<Cart> findByMemberId(String memberId);}
