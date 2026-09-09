package com.cosmetic.shopbackend.commerce;

import com.cosmetic.shopbackend.brand.BrandRepository;
import com.cosmetic.shopbackend.brand.BrandStatus;
import com.cosmetic.shopbackend.catalog.Product;
import com.cosmetic.shopbackend.catalog.ProductRepository;
import com.cosmetic.shopbackend.catalog.ProductVariant;
import com.cosmetic.shopbackend.catalog.ProductVariantRepository;
import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@RestController
@RequestMapping("/api")
public class CommerceController {
    private final CartRepository carts;
    private final CartItemRepository cartItems;
    private final ProductVariantRepository variants;
    private final ProductRepository products;
    private final ShopOrderRepository orders;
    private final OrderItemRepository orderItems;
    private final BrandRepository brands;

    public CommerceController(
            CartRepository carts,
            CartItemRepository cartItems,
            ProductVariantRepository variants,
            ProductRepository products,
            ShopOrderRepository orders,
            OrderItemRepository orderItems,
            BrandRepository brands
    ) {
        this.carts = carts;
        this.cartItems = cartItems;
        this.variants = variants;
        this.products = products;
        this.orders = orders;
        this.orderItems = orderItems;
        this.brands = brands;
    }

    public record CartRequest(String variantId, int quantity) {}
    public record OrderRequest(String idempotencyKey) {}

    @GetMapping("/cart")
    public Map<String, Object> view(
            @AuthenticationPrincipal ShopPrincipal actor
    ) {
        requireMember(actor); Cart cart = cart(actor.accountId());
        return Map.of("cartId", cart.getId(), "items", cartItems.findByCartId(cart.getId()));
    }

    @PostMapping("/cart/items")
    @Transactional
    public ResponseEntity<?> add(
            @AuthenticationPrincipal ShopPrincipal actor,
            @RequestBody CartRequest request
    ) {
        requireMember(actor);
        if (request.quantity() < 1 || request.variantId() == null) {
            return ResponseEntity.badRequest().body("invalid cart item");
        }
        if (activeVariant(request.variantId()).isEmpty()) {
            return ResponseEntity.status(HttpStatus.CONFLICT).body("inactive or unavailable product");
        }

        Cart cart = cart(actor.accountId());
        cartItems.addQuantity(UUID.randomUUID().toString(), cart.getId(), request.variantId(), request.quantity());
        return ResponseEntity.ok(cartItems.findByCartIdAndVariantId(cart.getId(), request.variantId()).orElseThrow());
    }

    @DeleteMapping("/cart/items/{id}")
    public ResponseEntity<?> remove(
            @AuthenticationPrincipal ShopPrincipal actor,
            @PathVariable String id
    ) {
        requireMember(actor);
        return cartItems.findById(id)
                .filter(item -> carts.findById(item.getCartId())
                        .map(cart -> cart.getMemberId().equals(actor.accountId()))
                        .orElse(false))
                .map(item -> {
                    cartItems.delete(item);
                    return ResponseEntity.noContent().build();
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping("/orders")
    @Transactional
    public ResponseEntity<?> order(
            @AuthenticationPrincipal ShopPrincipal actor,
            @RequestBody OrderRequest request
    ) {
        requireMember(actor);
        if (request.idempotencyKey() == null || request.idempotencyKey().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        Optional<ShopOrder> existing = orders.findByMemberIdAndIdempotencyKey(actor.accountId(), request.idempotencyKey());
        if (existing.isPresent()) {
            List<CartItem> retryItems = carts.findByMemberId(actor.accountId())
                    .map(cart -> cartItems.findByCartId(cart.getId())).orElseGet(List::of);
            if (!retryItems.isEmpty() && !existing.get().getRequestHash().equals(hash(retryItems))) {
                return ResponseEntity.status(HttpStatus.CONFLICT).body("idempotency key reused with different cart");
            }
            return ResponseEntity.ok(existing.get());
        }

        Cart cart = cart(actor.accountId());
        List<CartItem> items = cartItems.findByCartId(cart.getId());
        if (items.isEmpty()) {
            return ResponseEntity.badRequest().body("cart is empty");
        }

        String orderId = UUID.randomUUID().toString();
        BigDecimal total = BigDecimal.ZERO;
        List<OrderItem> snapshots = new ArrayList<>();
        for (CartItem cartItem : items) {
            ProductVariant variant = activeVariant(cartItem.getVariantId())
                    .orElseThrow(() -> new ResponseStatusException(HttpStatus.CONFLICT, "inactive or unavailable product"));
            Product product = products.findById(variant.getProductId()).orElseThrow();
            String brandName = brands.findById(product.getBrandId())
                    .map(brand -> brand.getName())
                    .orElseThrow(() -> new ResponseStatusException(HttpStatus.CONFLICT, "brand unavailable"));
            BigDecimal lineAmount = variant.unitPrice().multiply(BigDecimal.valueOf(cartItem.getQuantity()));
            total = total.add(lineAmount);
            snapshots.add(new OrderItem(
                    UUID.randomUUID().toString(), orderId, variant.getId(), product.getId(), product.getBrandId(),
                    product.getName(), brandName, variant.getSku(), variant.getLabel(), variant.unitPrice(), cartItem.getQuantity()
            ));
        }

        ShopOrder order = orders.save(new ShopOrder(
                orderId, actor.accountId(), request.idempotencyKey(), hash(items), total
        ));
        orderItems.saveAll(snapshots);
        cartItems.deleteByCartId(cart.getId());
        return ResponseEntity.status(HttpStatus.CREATED).body(order);
    }

    @PostMapping("/orders/{id}/pay")
    @Transactional
    public ResponseEntity<?> pay(
            @AuthenticationPrincipal ShopPrincipal actor,
            @PathVariable String id
    ) {
        requireMember(actor);
        Optional<ShopOrder> order = orders.findById(id);
        if (order.isEmpty() || !order.get().getMemberId().equals(actor.accountId())) return ResponseEntity.notFound().build();
        orders.markPaid(id, actor.accountId());
        return ResponseEntity.ok(orders.findById(id).orElseThrow());
    }

    private Cart cart(String memberId) {
        return carts.findByMemberId(memberId)
                .orElseGet(() -> carts.save(new Cart(UUID.randomUUID().toString(), memberId)));
    }

    private Optional<ProductVariant> activeVariant(String variantId) {
        return variants.findById(variantId)
                .filter(variant -> variant.getStatus() == ProductVariant.Status.ACTIVE)
                .filter(variant -> products.findById(variant.getProductId())
                        .filter(product -> product.getStatus() == Product.Status.ACTIVE)
                        .flatMap(product -> brands.findById(product.getBrandId()))
                        .map(brand -> brand.getStatus() == BrandStatus.ACTIVE)
                        .orElse(false));
    }

    private void requireMember(ShopPrincipal actor) {
        if (actor == null || actor.role() != AccountRole.MEMBER) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "member role required");
    }

    private String hash(List<CartItem> items) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            String source = items.stream()
                    .map(item -> item.getVariantId() + ":" + item.getQuantity())
                    .sorted()
                    .reduce("", String::concat);
            return HexFormat.of().formatHex(digest.digest(source.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new IllegalStateException(exception);
        }
    }
}
