package com.cosmetic.shopbackend.dashboard;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.cosmetic.shopbackend.brand.Brand;
import com.cosmetic.shopbackend.brand.BrandRepository;
import com.cosmetic.shopbackend.brand.SellerBrandResolver;
import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class DashboardControllerTest {
  private final DashboardMartService marts = mock(DashboardMartService.class);
  private final BrandRepository brands = mock(BrandRepository.class);
  private final DashboardController controller =
    new DashboardController(marts, new SellerBrandResolver(brands));

  @Test
  void positionApisUseBrandFromJwtPrincipal() {
    ShopPrincipal seller = new ShopPrincipal("seller-1", AccountRole.SELLER, "brand-1");
    when(marts.pricePosition("seller-1", "brand-1")).thenReturn(Map.of("brand_id", "brand-1"));
    when(marts.cohortPosition("seller-1", "brand-1", null, null, null)).thenReturn(Map.of("brand_id", "brand-1"));

    assertEquals("brand-1", controller.pricePosition(seller).get("brand_id"));
    assertEquals("brand-1", controller.cohortPosition(seller, null, null, null).get("brand_id"));
    verify(marts).pricePosition("seller-1", "brand-1");
    verify(marts).cohortPosition("seller-1", "brand-1", null, null, null);
  }

  @Test
  void positionApisFallBackToSellersBrandWhenClaimIsMissing() {
    // 로그인 뒤에 브랜드를 만든 판매자: 토큰에 brand_id 가 없어도 DB 의 브랜드로 읽는다
    Brand brand = new Brand();
    brand.setId("brand-new");
    when(brands.findAllBySeller_Id("seller-1")).thenReturn(List.of(brand));
    when(marts.pricePosition("seller-1", "brand-new")).thenReturn(Map.of("brand_id", "brand-new"));

    ShopPrincipal seller = new ShopPrincipal("seller-1", AccountRole.SELLER);
    assertEquals("brand-new", controller.pricePosition(seller).get("brand_id"));
  }

  @Test
  void positionApisRejectSellerWithoutAnyBrand() {
    when(brands.findAllBySeller_Id("seller-1")).thenReturn(List.of());
    ShopPrincipal seller = new ShopPrincipal("seller-1", AccountRole.SELLER);
    assertThrows(ResponseStatusException.class, () -> controller.pricePosition(seller));
    assertThrows(ResponseStatusException.class, () -> controller.cohortPosition(seller, null, null, null));
  }
}
