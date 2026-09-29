package com.cosmetic.shopbackend.brand;

import com.cosmetic.shopbackend.identity.*;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.util.*;
import org.springframework.http.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/brands")
public class BrandController {

  private final BrandRepository brands;
  private final SellerAccountRepository sellers;

  public BrandController(BrandRepository b, SellerAccountRepository s) {
    brands = b;
    sellers = s;
  }

  public record BrandRequest(
    @NotBlank String name,
    String description,
    String logoUrl
  ) {}

  public record BrandResponse(
    String id,
    String sellerAccountId,
    String name,
    String description,
    String logoUrl,
    String status
  ) {}

  @GetMapping
  public List<BrandResponse> list(
    @AuthenticationPrincipal ShopPrincipal actor
  ) {
    if (actor.role() == AccountRole.ADMIN) return brands
      .findAll()
      .stream()
      .map(BrandController::view)
      .toList();
    return brands
      .findAllBySeller_Id(actor.accountId())
      .stream()
      .map(BrandController::view)
      .toList();
  }

  @PostMapping
  public ResponseEntity<BrandResponse> create(
    @AuthenticationPrincipal ShopPrincipal actor,
    @Valid @RequestBody BrandRequest r
  ) {
    if (actor.role() != AccountRole.SELLER) throw new ResponseStatusException(
      HttpStatus.FORBIDDEN
    );
    Brand b = new Brand();
    b.setSeller(
      sellers
        .findById(actor.accountId())
        .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED))
    );
    copy(b, r);
    brands.save(b);
    return ResponseEntity.status(HttpStatus.CREATED).body(view(b));
  }

  @GetMapping("/{id}")
  public BrandResponse get(
    @PathVariable String id,
    @AuthenticationPrincipal ShopPrincipal actor
  ) {
    return view(authorized(id, actor));
  }

  @PutMapping("/{id}")
  public BrandResponse update(
    @PathVariable String id,
    @AuthenticationPrincipal ShopPrincipal actor,
    @Valid @RequestBody BrandRequest r
  ) {
    Brand b = authorized(id, actor);
    copy(b, r);
    return view(brands.save(b));
  }

  @PatchMapping("/{id}/status")
  public BrandResponse status(
    @PathVariable String id,
    @RequestParam BrandStatus status,
    @AuthenticationPrincipal ShopPrincipal actor
  ) {
    Brand b = authorized(id, actor);
    if (
      actor.role() == AccountRole.SELLER &&
      !sellerMayChangeStatus(b.getStatus(), status)
    ) throw new ResponseStatusException(
      HttpStatus.FORBIDDEN,
      "비활성 브랜드를 다시 여는 것은 운영자만 할 수 있어요."
    );
    b.setStatus(status);
    return view(brands.save(b));
  }

  /**
   * 판매자가 자기 브랜드 상태를 바꿀 수 있는가.
   *
   * 판매자는 브랜드를 내리는 것(INACTIVE)만 할 수 있다. INACTIVE 는 운영자가 내린 것인지 판매자가
   * 내린 것인지 구분할 컬럼이 없으므로, INACTIVE → ACTIVE 로 되살리는 것은 운영자
   * (`PATCH /api/admin/brands/{id}/status`)만 한다. 같은 상태로 두는 것은 막지 않는다.
   */
  static boolean sellerMayChangeStatus(BrandStatus current, BrandStatus next) {
    if (next == current) return true;
    return next == BrandStatus.INACTIVE;
  }

  private Brand authorized(String id, ShopPrincipal actor) {
    if (actor.role() == AccountRole.ADMIN) return brands
      .findById(id)
      .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    if (actor.role() != AccountRole.SELLER) throw new ResponseStatusException(
      HttpStatus.FORBIDDEN
    );
    return brands
      .findByIdAndSeller_Id(id, actor.accountId())
      .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
  }

  private static void copy(Brand b, BrandRequest r) {
    if (!validLogoUrl(r.logoUrl())) throw new ResponseStatusException(
      HttpStatus.BAD_REQUEST,
      "로고 주소는 https:// 로 시작하는 주소나 /images 같은 사이트 안 경로만 쓸 수 있어요."
    );
    b.setName(r.name());
    b.setDescription(r.description());
    b.setLogoUrl(r.logoUrl());
  }

  /**
   * 로고 주소로 받아 줄 값인가. 쓸 때(생성·수정)만 본다 — 이미 저장된 값은 읽을 때 막지 않는다.
   *
   * 비어 있으면 로고 없음이다. 그 밖에는 호스트가 있는 `https://` 주소나 `/` 로 시작하는 사이트 안
   * 경로만 받는다. `javascript:`·`data:`·`http://`·`//다른호스트` 같은 값은 400 이다.
   */
  static boolean validLogoUrl(String url) {
    if (url == null || url.isBlank()) return true;
    String v = url.trim();
    if (v.startsWith("/")) return !v.startsWith("//") && !v.contains("\\");
    try {
      java.net.URI u = new java.net.URI(v);
      return (
        "https".equalsIgnoreCase(u.getScheme()) &&
        u.getHost() != null &&
        !u.getHost().isBlank()
      );
    } catch (java.net.URISyntaxException e) {
      return false;
    }
  }

  private static BrandResponse view(Brand b) {
    return new BrandResponse(
      b.getId(),
      b.getSeller().getId(),
      b.getName(),
      b.getDescription(),
      b.getLogoUrl(),
      b.getStatus().name()
    );
  }
}
