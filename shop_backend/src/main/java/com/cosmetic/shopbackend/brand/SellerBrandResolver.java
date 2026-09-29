package com.cosmetic.shopbackend.brand;

import com.cosmetic.shopbackend.security.ShopPrincipal;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/**
 * 판매자의 브랜드를 정한다. JWT 의 brand_id 클레임은 로그인 때만 채워져서, 로그인 뒤에 브랜드를 만든
 * 판매자는 다시 로그인하기 전까지 클레임이 비어 있다. 그때는 DB 에서 판매자의 브랜드를 찾는다
 * (로그인 때 클레임을 채우는 것과 같은 조회).
 */
@Component
public class SellerBrandResolver {

  private final BrandRepository brands;

  public SellerBrandResolver(BrandRepository brands) {
    this.brands = brands;
  }

  public String brandIdOf(ShopPrincipal seller) {
    String claim = seller.brandId();
    if (claim != null && !claim.isBlank()) return claim;
    return brands.findAllBySeller_Id(seller.accountId()).stream()
      .map(Brand::getId)
      .findFirst()
      .orElseThrow(() ->
        new ResponseStatusException(HttpStatus.FORBIDDEN, "brand claim required")
      );
  }
}
