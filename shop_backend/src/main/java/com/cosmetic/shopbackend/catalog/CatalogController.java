package com.cosmetic.shopbackend.catalog;

import com.cosmetic.shopbackend.brand.*;
import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.security.ShopPrincipal;
import tools.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.*;
import java.util.*;
import java.util.Locale;
import org.springframework.http.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

@RestController
@RequestMapping("/api/products")
@Transactional
@Tag(name = "상품", description = "상품 조회와 판매자 상품 등록·수정 API")
public class CatalogController {

  private final ProductRepository products;
  private final ProductVariantRepository variants;
  private final BrandRepository brands;
  private final ProductUnmappedValueRepository unmapped;
  private final ObjectMapper mapper;
  private final JdbcTemplate jdbc;

  public CatalogController(
    ProductRepository p,
    ProductVariantRepository v,
    BrandRepository b,
    ProductUnmappedValueRepository u,
    ObjectMapper m,
    JdbcTemplate jdbc
  ) {
    products = p;
    variants = v;
    brands = b;
    unmapped = u;
    mapper = m;
    this.jdbc = jdbc;
  }

  @GetMapping
  @Operation(summary = "상품 목록 조회", description = "활성 브랜드의 판매 중인 상품 목록을 조회합니다. Accept-Language가 ko이면 한국어 정보를 우선 반환합니다.")
  public List<ProductSummary> list(Locale locale) {
    List<Product> visibleProducts = products
      .findByStatus(Product.Status.ACTIVE)
      .stream()
      .filter(this::visible)
      .toList();
    Map<String, List<String>> highlightsByProductId = productHighlightsById(
      visibleProducts.stream().map(Product::getId).toList()
    );
    return visibleProducts.stream()
      .map(p -> summary(p, locale, highlightsByProductId.getOrDefault(p.getId(), List.of())))
      .toList();
  }

  @GetMapping("/{id}")
  @Operation(summary = "상품 상세 조회", description = "상품 상세, 옵션, 갤러리 이미지, 성분과 다국어 설명을 조회합니다.")
  public ProductDetail get(@PathVariable String id, Locale locale) {
    Product p = products
      .findById(id)
      .filter(this::visible)
      .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    return detail(p, locale);
  }

  public record ProductRequest(
    @NotBlank String brandId,
    @NotBlank String categoryId,
    @NotBlank String productName,
    @NotBlank String secondaryCategory,
    @NotBlank String tertiaryCategory,
    List<String> highlights,
    @NotBlank String ingredients,
    @NotNull @DecimalMin("1") BigDecimal priceKrw,
    String size,
    String primaryImageUrl,
    Map<String, Object> description
  ) {}

  public record ProductSummary(
    String productId,
    String brandId,
    String brandName,
    String categoryId,
    String productName,
    String productNameKo,
    String secondaryCategory,
    String tertiaryCategory,
    BigDecimal priceKrw,
    BigDecimal salePriceKrw,
    String sizeKo,
    String ingredientsTextKo,
    Map<String, Object> descriptionKo,
    List<String> badges,
    String priceBin,
    BigDecimal rating,
    Integer lovesCount,
    String primaryImageUrl,
    List<String> highlights,
    /** 구매 화면이 백엔드 variant_id를 바로 쓸 수 있도록 목록에도 포함한다. */
    List<VariantView> variants
  ) {}

  public record VariantView(
    String variantId,
    String skuId,
    String label,
    String size,
    String sizeKo,
    String labelKo,
    BigDecimal priceKrw,
    BigDecimal salePriceKrw,
    String imageUrl,
    String swatchUrl,
    String status
  ) {}

  public record ImageView(String imageId, String url, int sortOrder) {}

  /** 상품-성분 연결에서 읽은 표준 성분 코드와 표시용 한글 라벨. */
  private record IngredientLabel(String code, String labelKo) {}

  /** concern·clean·texture 연결 테이블을 API highlights 형식으로 합치기 위한 내부 행. */
  private record HighlightRow(String productId, String code) {}

  public record ProductDetail(
    ProductSummary product,
    List<VariantView> variants,
    List<ImageView> images,
    String ingredients,
    String ingredientsKo,
    String ingredientsText,
    String ingredientsTextKo,
    Map<String, Object> description
    ,Map<String, Object> descriptionKo
  ) {}

  @PostMapping
  public ResponseEntity<ProductDetail> create(
    @AuthenticationPrincipal ShopPrincipal actor,
    @Valid @RequestBody ProductRequest r,
    Locale locale
  ) {
    requireOwner(actor, r.brandId());
    validate(r);
    Product p = new Product(
      UUID.randomUUID().toString(),
      r.brandId(),
      r.categoryId(),
      r.productName()
    );
    p.update(input(r), defaultRating(r.tertiaryCategory()));
    p = products.save(p);
    saveUnmapped(p.getId(), r.highlights());
    ProductVariant variant = new ProductVariant(
        UUID.randomUUID().toString(),
        p.getId(),
        "SKU-" + UUID.randomUUID().toString().substring(0, 8),
        "기본 옵션",
        r.priceKrw(),
        null
      );
    variant.setSize(r.size());
    variants.save(variant);
    return ResponseEntity.status(HttpStatus.CREATED).body(detail(p, locale));
  }

  @PutMapping("/{id}")
  public ProductDetail update(
    @AuthenticationPrincipal ShopPrincipal actor,
    @PathVariable String id,
    @Valid @RequestBody ProductRequest r,
    Locale locale
  ) {
    Product p = products
      .findById(id)
      .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    requireOwner(actor, p.getBrandId());
    if (!p.getBrandId().equals(r.brandId())) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "상품의 브랜드는 변경할 수 없습니다");
    }
    validate(r);
    p.update(input(r), defaultRating(r.tertiaryCategory()));
    Product saved = products.save(p);
    saveUnmapped(saved.getId(), r.highlights());
    variants
      .findFirstByProductIdAndLabel(saved.getId(), "기본 옵션")
      .ifPresent(v -> {
        v.updateBasePrice(r.priceKrw());
        v.setSize(r.size());
        variants.save(v);
      });
    return detail(saved, locale);
  }

  @DeleteMapping("/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  @Operation(summary = "판매자 상품 삭제", description = "판매자가 자신의 브랜드 상품을 비활성화합니다.")
  public void delete(
    @AuthenticationPrincipal ShopPrincipal actor,
    @PathVariable String id
  ) {
    Product p = products
      .findById(id)
      .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    requireOwner(actor, p.getBrandId());
    // 주문·리뷰 등 기존 참조를 보존하기 위해 물리 삭제 대신 비활성화합니다.
    p.status(Product.Status.INACTIVE);
    products.save(p);
  }

  @PatchMapping("/{id}/status")
  public Product status(
    @AuthenticationPrincipal ShopPrincipal actor,
    @PathVariable String id,
    @RequestParam Product.Status value
  ) {
    Product p = products
      .findById(id)
      .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    requireOwner(actor, p.getBrandId());
    p.status(value);
    return products.save(p);
  }

  private ProductContract.ProductInput input(ProductRequest r) {
    try {
      return new ProductContract.ProductInput(
        r.productName(),
        r.categoryId(),
        r.secondaryCategory(),
        r.tertiaryCategory(),
        r.highlights() == null ? List.of() : r.highlights(),
        r.ingredients(),
        r.priceKrw(),
        r.primaryImageUrl(),
        r.description == null ? null : mapper.writeValueAsString(r.description)
      );
    } catch (Exception e) {
      throw new ResponseStatusException(
        HttpStatus.BAD_REQUEST,
        "description 형식이 올바르지 않습니다"
      );
    }
  }

  private void validate(ProductRequest r) {
    if (
      !ProductContract.SECONDARY.contains(r.secondaryCategory()) ||
      !ProductContract.TERTIARY.contains(r.tertiaryCategory())
    ) throw new ResponseStatusException(
      HttpStatus.BAD_REQUEST,
      "카테고리가 계약 어휘에 없습니다"
    );
    if (
      jdbc.queryForObject(
        "select count(*) from category where category_id=? and is_active=true",
        Integer.class,
        r.categoryId()
      ) == 0
    ) throw new ResponseStatusException(
      HttpStatus.BAD_REQUEST,
      "활성 카테고리가 아닙니다"
    );
  }

  private BigDecimal defaultRating(String tertiary) {
    List<BigDecimal> scoped = products.ratingsByTertiary(tertiary);
    List<BigDecimal> values =
      scoped.size() >= 3 ? scoped : products.allRatings();
    if (values.isEmpty()) return BigDecimal.valueOf(4.0);
    values = new ArrayList<>(values);
    values.sort(Comparator.naturalOrder());
    int n = values.size(),
      mid = n / 2;
    return n % 2 == 1
      ? values.get(mid)
      : values
          .get(mid - 1)
          .add(values.get(mid))
          .divide(BigDecimal.valueOf(2), 2, RoundingMode.HALF_UP);
  }

  private void saveUnmapped(String productId, List<String> values) {
    for (String value : values == null ? List.<String>of() : values)
      if (!ProductContract.isKnownHighlight(value)) unmapped.save(
        new ProductUnmappedValue(productId, "highlights", value)
      );
  }

  private void requireOwner(ShopPrincipal actor, String brandId) {
    if (
      actor == null ||
      actor.role() != AccountRole.SELLER ||
      brands.findByIdAndSeller_Id(brandId, actor.accountId()).isEmpty()
    ) throw new ResponseStatusException(HttpStatus.FORBIDDEN);
  }

  private boolean visible(Product p) {
    return (
      p.getStatus() == Product.Status.ACTIVE &&
      brands
        .findById(p.getBrandId())
        .map(b -> b.getStatus() == BrandStatus.ACTIVE)
        .orElse(false)
    );
  }

  private ProductSummary summary(Product p, Locale locale, List<String> highlights) {
    Brand b = brands.findById(p.getBrandId()).orElse(null);
    List<ProductVariant> activeVariants = variants
      .findByProductId(p.getId())
      .stream()
      .filter(v -> v.getStatus() == ProductVariant.Status.ACTIVE)
      .toList();
    BigDecimal price = activeVariants.stream().map(ProductVariant::getPrice)
      .filter(Objects::nonNull).min(Comparator.naturalOrder()).orElse(null);
    BigDecimal salePrice = activeVariants.stream().map(ProductVariant::getSalePrice)
      .filter(Objects::nonNull).min(Comparator.naturalOrder()).orElse(null);
    return new ProductSummary(
      p.getId(),
      p.getBrandId(),
      b == null ? null : b.getName(),
      p.getCategoryId(),
      localized(p.getNameKo(), p.getName(), locale),
      p.getNameKo(),
      p.getSecondaryCategory(),
      p.getTertiaryCategory(),
      price,
      salePrice,
      p.getSizeKo(),
      p.getIngredientsTextKo(),
      jsonMap(p.getDescriptionKoJson()),
      jsonList(p.getBadgesJson()),
      p.getPriceBin(),
      p.getRating(),
      p.getLovesCount(),
      p.getPrimaryImageUrl(),
      highlights,
      variantViews(activeVariants)
    );
  }

  private List<VariantView> variantViews(List<ProductVariant> values) {
    return values
      .stream()
      .map(v ->
        new VariantView(
          v.getId(),
          v.getSku(),
          v.getLabel(),
          v.getSize(),
          v.getSize(),
          null,
          v.getPrice(),
          v.getSalePrice(),
          v.getImageUrl(),
          v.getSwatchUrl(),
          v.getStatus().name()
        )
      )
      .toList();
  }

  private ProductDetail detail(Product p, Locale locale) {
    Map<String, Object> d = null;
    try {
      if (p.getDescriptionJson() != null) d = mapper.readValue(
        p.getDescriptionJson(),
        Map.class
      );
    } catch (Exception ignored) {}
    List<VariantView> vs = variantViews(
      variants
        .findByProductId(p.getId())
        .stream()
        .filter(v -> v.getStatus() == ProductVariant.Status.ACTIVE)
        .toList()
    );
    List<ImageView> images = jdbc.query(
      "select image_id,url,sort_order from product_image where product_id=? order by sort_order",
      (rs, rowNum) -> new ImageView(rs.getString("image_id"), rs.getString("url"), rs.getInt("sort_order")),
      p.getId()
    );
    List<IngredientLabel> ingredientLabels = ingredientLabels(p.getId());
    boolean ko = isKorean(locale);
    return new ProductDetail(summary(p, locale, productHighlights(p.getId())), vs, images,
      ingredientText(ingredientLabels, ko),
      ingredientText(ingredientLabels, true),
      localized(p.getIngredientsTextKo(), p.getIngredientsText(), locale),
      p.getIngredientsTextKo(), ko ? jsonMap(p.getDescriptionKoJson()) : d,
      jsonMap(p.getDescriptionKoJson()));
  }

  private List<String> productHighlights(String productId) {
    return productHighlightsById(List.of(productId)).getOrDefault(productId, List.of());
  }

  /**
   * JPA entity의 collection이 아니라 정규화된 concern·clean·texture 연결 테이블을 읽는다.
   * 목록에서는 모든 상품 ID를 한 번에 조회해 상품별 추가 쿼리가 생기지 않게 한다.
   */
  private Map<String, List<String>> productHighlightsById(List<String> productIds) {
    if (productIds.isEmpty()) return Map.of();
    String placeholders = String.join(",", Collections.nCopies(productIds.size(), "?"));
    String sql = """
      select feature.product_id, feature.code
      from (
        select pc.product_id, pc.concern_code as code, 1 as feature_order
        from product_concern pc
        union all
        select pc.product_id, pc.clean_code as code, 2 as feature_order
        from product_clean pc
        join clean_feature cf on cf.code = pc.clean_code and cf.is_active = true
        union all
        select pt.product_id, pt.texture_code as code, 3 as feature_order
        from product_texture pt
        join texture_feature tf on tf.code = pt.texture_code and tf.is_active = true
      ) feature
      where feature.product_id in (%s)
      order by feature.product_id, feature.feature_order, feature.code
      """.formatted(placeholders);
    Map<String, List<String>> result = new HashMap<>();
    for (String productId : productIds) result.put(productId, new ArrayList<>());
    List<HighlightRow> rows = jdbc.query(
      sql,
      (rs, rowNum) -> new HighlightRow(rs.getString("product_id"), rs.getString("code")),
      productIds.toArray()
    );
    for (HighlightRow row : rows) result.get(row.productId()).add(row.code());
    return result;
  }

  /**
   * 전성분 원문(product.ingredients_text)을 API 응답에 쓰지 않는다.
   * 정규화된 연결 테이블을 기준으로, 파서가 기록한 원래 등장 순서가 있으면 그 순서를 보존한다.
   */
  private List<IngredientLabel> ingredientLabels(String productId) {
    return jdbc.query(
      """
      select pi.ingredient_code, i.label_ko
      from product_ingredient pi
      join ingredient i on i.ingredient_code = pi.ingredient_code
      where pi.product_id = ? and i.is_active = true
      order by pi.first_position is null, pi.first_position, pi.ingredient_code
      """,
      (rs, rowNum) -> new IngredientLabel(rs.getString("ingredient_code"), rs.getString("label_ko")),
      productId
    );
  }

  /** 기존 프론트 계약이 문자열이므로, 조인 결과를 쉼표 구분 문자열로 반환한다. */
  private String ingredientText(List<IngredientLabel> labels, boolean korean) {
    return labels.stream()
      .map(label -> korean ? label.labelKo() : label.code())
      .collect(java.util.stream.Collectors.joining(", "));
  }

  private String localized(String korean, String english, Locale locale) {
    return isKorean(locale) && korean != null && !korean.isBlank() ? korean : english;
  }

  private boolean isKorean(Locale locale) { return locale != null && "ko".equalsIgnoreCase(locale.getLanguage()); }

  private Map<String, Object> jsonMap(String raw) {
    if (raw == null || raw.isBlank()) return null;
    try { return mapper.readValue(raw, Map.class); } catch (Exception ignored) { return null; }
  }

  private List<String> jsonList(String raw) {
    if (raw == null || raw.isBlank()) return List.of();
    try { return mapper.readValue(raw, mapper.getTypeFactory().constructCollectionType(List.class, String.class)); }
    catch (Exception ignored) { return List.of(); }
  }
}
