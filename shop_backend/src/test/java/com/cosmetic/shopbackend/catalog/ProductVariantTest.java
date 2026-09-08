package com.cosmetic.shopbackend.catalog;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ProductVariantTest {
    @Test
    void unitPriceUsesSalePriceWhenPresent() {
        ProductVariant variant = new ProductVariant("v-1", "p-1", "sku-1", "Shade",
                BigDecimal.valueOf(20000), BigDecimal.valueOf(15000));

        assertEquals(BigDecimal.valueOf(15000), variant.unitPrice());
    }

    @Test
    void unitPriceFallsBackToRegularPriceWithoutSalePrice() {
        ProductVariant variant = new ProductVariant("v-1", "p-1", "sku-1", "Shade",
                BigDecimal.valueOf(20000), null);

        assertEquals(BigDecimal.valueOf(20000), variant.unitPrice());
    }
}
