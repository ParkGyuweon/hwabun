package com.cosmetic.shopbackend.commerce;
import org.springframework.data.jpa.repository.*; import org.springframework.data.repository.query.Param; import java.util.*;
public interface CartItemRepository extends JpaRepository<CartItem,String>{
 List<CartItem> findByCartId(String cartId); Optional<CartItem> findByCartIdAndVariantId(String c,String v); void deleteByCartId(String c);
 @Modifying @Query(value="insert ignore into cart_item(cart_item_id,cart_id,variant_id,quantity) values(:id,:cartId,:variantId,0)",nativeQuery=true)
 int insertIfAbsent(@Param("id") String id,@Param("cartId") String cartId,@Param("variantId") String variantId);
 @Modifying @Query("update CartItem i set i.quantity = i.quantity + :quantity where i.cartId = :cartId and i.variantId = :variantId")
 int incrementQuantity(@Param("cartId") String cartId,@Param("variantId") String variantId,@Param("quantity") int quantity);
}
