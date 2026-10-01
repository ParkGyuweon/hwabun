package com.cosmetic.shopbackend.commerce;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.cosmetic.shopbackend.brand.Brand;
import com.cosmetic.shopbackend.brand.BrandRepository;
import com.cosmetic.shopbackend.brand.BrandStatus;
import com.cosmetic.shopbackend.catalog.Product;
import com.cosmetic.shopbackend.catalog.ProductRepository;
import com.cosmetic.shopbackend.catalog.ProductVariant;
import com.cosmetic.shopbackend.catalog.ProductVariantRepository;
import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.util.ReflectionTestUtils;

class CommerceOrderSelectionTest {
  private final CartRepository carts = mock(CartRepository.class);
  private final CartItemRepository cartItems = mock(CartItemRepository.class);
  private final ProductVariantRepository variants = mock(ProductVariantRepository.class);
  private final ProductRepository products = mock(ProductRepository.class);
  private final ShopOrderRepository orders = mock(ShopOrderRepository.class);
  private final OrderItemRepository orderItems = mock(OrderItemRepository.class);
  private final BrandRepository brands = mock(BrandRepository.class);
  private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
  private final CommerceController controller = new CommerceController(
    carts, cartItems, variants, products, orders, orderItems, brands, jdbc
  );

  @Test
  void explicitItemsOrderDoesNotReadOrClearExistingCart() {
    ProductVariant variant = new ProductVariant("variant-1", "product-1", "sku-1", "기본", BigDecimal.valueOf(1000), null);
    Product product = mock(Product.class);
    Brand brand = mock(Brand.class);
    when(product.getId()).thenReturn("product-1");
    when(product.getBrandId()).thenReturn("brand-1");
    when(product.getName()).thenReturn("상품");
    when(product.getStatus()).thenReturn(Product.Status.ACTIVE);
    when(brand.getName()).thenReturn("브랜드");
    when(brand.getStatus()).thenReturn(BrandStatus.ACTIVE);
    when(variants.findById("variant-1")).thenReturn(Optional.of(variant));
    when(products.findById("product-1")).thenReturn(Optional.of(product));
    when(brands.findById("brand-1")).thenReturn(Optional.of(brand));
    when(orders.save(any(ShopOrder.class))).thenAnswer(call -> call.getArgument(0));
    when(orderItems.findByOrderId(anyString())).thenReturn(List.of());

    var result = controller.order(
      new ShopPrincipal("member-1", AccountRole.MEMBER),
      new CommerceController.OrderRequest("key-1", List.of(new CommerceController.OrderLineRequest("variant-1", 2)), false)
    );

    assertEquals(HttpStatus.CREATED, result.getStatusCode());
    verify(carts, never()).findByMemberId(anyString());
    verify(cartItems, never()).findByCartId(anyString());
    verify(cartItems, never()).deleteByCartId(anyString());
    verify(orders).save(argThat(order -> order.getTotalAmount().compareTo(BigDecimal.valueOf(2000)) == 0));
  }

  @Test
  void testPaymentClearsCartOnlyOnFirstPaidTransition() {
    ReflectionTestUtils.setField(controller, "testPayAllowedMemberPrefix", "member-");
    ShopOrder order = new ShopOrder("order-1", "member-1", "key-1", "T" + "0".repeat(63), BigDecimal.TEN);
    Cart cart = mock(Cart.class);
    when(cart.getId()).thenReturn("cart-1");
    when(orders.findById("order-1")).thenReturn(Optional.of(order));
    when(orders.markPaid(eq("order-1"), eq("member-1"), any())).thenReturn(1, 0);
    when(carts.findByMemberId("member-1")).thenReturn(Optional.of(cart));
    ShopPrincipal member = new ShopPrincipal("member-1", AccountRole.MEMBER);

    controller.pay(member, "order-1");
    controller.pay(member, "order-1");

    verify(jdbc).update(
      contains("delete ci from cart_item ci"),
      eq("order-1"),
      eq("member-1")
    );
    verify(jdbc).update(
      contains("update cart_item ci"),
      eq("order-1"),
      eq("member-1")
    );
  }

}
