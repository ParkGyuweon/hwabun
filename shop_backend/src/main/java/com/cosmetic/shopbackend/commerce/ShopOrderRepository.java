package com.cosmetic.shopbackend.commerce; import org.springframework.data.jpa.repository.*; import java.util.*;
public interface ShopOrderRepository extends JpaRepository<ShopOrder,String>{Optional<ShopOrder> findByMemberIdAndIdempotencyKey(String m,String k);List<ShopOrder> findByMemberIdOrderByIdDesc(String m);}
