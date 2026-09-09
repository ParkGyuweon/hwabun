package com.cosmetic.shopbackend.catalog;

import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class ProductTest {

  @Test
  void updateKeepsExistingPopularity() {
    Product product = new Product("p", "b", "c", "old");
    product.update(
      new ProductContract.ProductInput(
        "new",
        "c",
        "Moisturizers",
        "Face Serums",
        List.of("Dryness"),
        "Water",
        BigDecimal.valueOf(26000),
        null,
        null
      ),
      BigDecimal.valueOf(4)
    );
    assertEquals(0, product.getLovesCount());
    product.update(
      new ProductContract.ProductInput(
        "newer",
        "c",
        "Moisturizers",
        "Face Serums",
        List.of(),
        "Water",
        BigDecimal.valueOf(30000),
        null,
        null
      ),
      BigDecimal.valueOf(4)
    );
    assertEquals(0, product.getLovesCount());
    assertEquals(Product.RatingSource.injected, product.getRatingSource());
  }
}
