package com.cosmetic.shopbackend.brand;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.identity.SellerAccountRepository;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

class BrandControllerTest {
  private final BrandController controller = new BrandController(
    mock(BrandRepository.class),
    mock(SellerAccountRepository.class)
  );
  private final BrandController.BrandRequest request =
    new BrandController.BrandRequest("새 브랜드", null, null);

  @Test
  void createWithoutActorIsUnauthorizedNotServerError() {
    ResponseStatusException exception = assertThrows(
      ResponseStatusException.class,
      () -> controller.create(null, request)
    );
    assertEquals(HttpStatus.UNAUTHORIZED, exception.getStatusCode());
  }

  @Test
  void createByNonSellerIsForbidden() {
    ResponseStatusException exception = assertThrows(
      ResponseStatusException.class,
      () -> controller.create(new ShopPrincipal("member-1", AccountRole.MEMBER), request)
    );
    assertEquals(HttpStatus.FORBIDDEN, exception.getStatusCode());
  }
}
