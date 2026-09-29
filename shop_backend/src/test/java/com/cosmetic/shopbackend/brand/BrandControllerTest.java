package com.cosmetic.shopbackend.brand;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.identity.SellerAccount;
import com.cosmetic.shopbackend.identity.SellerAccountRepository;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class BrandControllerTest {

  private static final ShopPrincipal SELLER = new ShopPrincipal(
    "seller-1",
    AccountRole.SELLER
  );
  private static final ShopPrincipal ADMIN = new ShopPrincipal(
    "admin-1",
    AccountRole.ADMIN
  );

  private BrandRepository brands;
  private BrandController controller;
  private Brand brand;

  @BeforeEach
  void setUp() {
    brands = mock(BrandRepository.class);
    controller = new BrandController(
      brands,
      mock(SellerAccountRepository.class)
    );
    SellerAccount seller = new SellerAccount();
    seller.setId("seller-1");
    brand = new Brand();
    brand.setId("b1");
    brand.setSeller(seller);
    brand.setName("브랜드");
    when(brands.findByIdAndSeller_Id("b1", "seller-1")).thenReturn(
      Optional.of(brand)
    );
    when(brands.findById("b1")).thenReturn(Optional.of(brand));
    when(brands.save(any(Brand.class))).thenAnswer(i -> i.getArgument(0));
  }

  @Test
  @DisplayName("판매자는 자기 브랜드를 내릴 수 있다")
  void sellerCanDeactivate() {
    assertEquals(
      "INACTIVE",
      controller.status("b1", BrandStatus.INACTIVE, SELLER).status()
    );
  }

  @Test
  @DisplayName("판매자는 비활성 브랜드를 다시 열 수 없다 — 운영자만 한다")
  void sellerCannotReactivate() {
    brand.setStatus(BrandStatus.INACTIVE);
    ResponseStatusException e = assertThrows(
      ResponseStatusException.class,
      () -> controller.status("b1", BrandStatus.ACTIVE, SELLER)
    );
    assertEquals(403, e.getStatusCode().value());
    assertEquals(BrandStatus.INACTIVE, brand.getStatus());
  }

  @Test
  @DisplayName("운영자는 비활성 브랜드를 다시 열 수 있다")
  void adminCanReactivate() {
    brand.setStatus(BrandStatus.INACTIVE);
    assertEquals(
      "ACTIVE",
      controller.status("b1", BrandStatus.ACTIVE, ADMIN).status()
    );
  }
}
