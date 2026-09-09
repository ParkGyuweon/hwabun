package com.cosmetic.shopbackend.commerce;

import java.util.*;
import org.springframework.data.jpa.repository.*;

public interface OrderItemRepository extends JpaRepository<OrderItem, String> {
  List<OrderItem> findByOrderId(String orderId);
}
