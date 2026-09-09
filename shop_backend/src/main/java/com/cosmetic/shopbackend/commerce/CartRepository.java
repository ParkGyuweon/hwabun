package com.cosmetic.shopbackend.commerce;

import java.util.*;
import org.springframework.data.jpa.repository.*;

public interface CartRepository extends JpaRepository<Cart, String> {
  Optional<Cart> findByMemberId(String memberId);
}
