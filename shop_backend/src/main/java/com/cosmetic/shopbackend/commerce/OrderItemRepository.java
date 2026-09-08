package com.cosmetic.shopbackend.commerce; import org.springframework.data.jpa.repository.*; import java.util.*;
public interface OrderItemRepository extends JpaRepository<OrderItem,String>{List<OrderItem> findByOrderId(String orderId);}
