package com.cosmetic.shopbackend.commerce; import org.springframework.data.jpa.repository.*; import java.util.*;
public interface CartItemRepository extends JpaRepository<CartItem,String>{List<CartItem> findByCartId(String cartId);Optional<CartItem> findByCartIdAndVariantId(String c,String v);void deleteByCartId(String c);}
