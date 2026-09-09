package com.cosmetic.shopbackend.catalog;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class ProductVariantTest {

  @Test
  void unitPriceUsesSalePriceWhenPresent() {
    ProductVariant variant = new ProductVariant(
      "v-1",
      "p-1",
      "sku-1",
      "Shade",
      BigDecimal.valueOf(20000),
      BigDecimal.valueOf(15000)
    );

    assertEquals(BigDecimal.valueOf(15000), variant.unitPrice());
  }

  @Test
  void unitPriceFallsBackToRegularPriceWithoutSalePrice() {
    ProductVariant variant = new ProductVariant(
      "v-1",
      "p-1",
      "sku-1",
      "Shade",
      BigDecimal.valueOf(20000),
      null
    );

    assertEquals(BigDecimal.valueOf(20000), variant.unitPrice());
  }

  @Test
  void basePriceUpdateEndsExistingMvpDiscount() {
    ProductVariant variant = new ProductVariant(
      "v-1",
      "p-1",
      "sku-1",
      "Default",
      BigDecimal.valueOf(20000),
      BigDecimal.valueOf(15000)
    );

    variant.updateBasePrice(BigDecimal.valueOf(25000));

    assertEquals(BigDecimal.valueOf(25000), variant.getPrice());
    assertEquals(null, variant.getSalePrice());
    assertEquals(BigDecimal.valueOf(25000), variant.unitPrice());
  }
}
