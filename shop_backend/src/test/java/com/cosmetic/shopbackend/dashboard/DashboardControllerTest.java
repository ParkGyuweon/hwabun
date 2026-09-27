package com.cosmetic.shopbackend.dashboard;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class DashboardControllerTest {
  private final DashboardMartService marts = mock(DashboardMartService.class);
  private final DashboardController controller = new DashboardController(marts);

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
  void positionApisRejectMissingBrandClaim() {
    ShopPrincipal seller = new ShopPrincipal("seller-1", AccountRole.SELLER);
    assertThrows(ResponseStatusException.class, () -> controller.pricePosition(seller));
    assertThrows(ResponseStatusException.class, () -> controller.cohortPosition(seller, null, null, null));
  }
}
