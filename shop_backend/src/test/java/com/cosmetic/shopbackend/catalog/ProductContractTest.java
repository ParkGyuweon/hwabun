package com.cosmetic.shopbackend.catalog;

import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.util.List;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class ProductContractTest {
    @Test
    void convertsKrwToUsdAndAssignsContractPriceBin() {
        assertEquals(new BigDecimal("20.00"), ProductContract.usd(new BigDecimal("26000")));
        assertEquals("20-35", ProductContract.priceBin(new BigDecimal("20.00")));
        assertEquals("80+", ProductContract.priceBin(new BigDecimal("80.00")));
    }

    @Test
    void highlightsAreSplitIntoContractAttributeGroups() {
        assertEquals(Set.of("Dryness"), ProductContract.group(List.of("Dryness", "Hydrating"), ProductContract.CONCERNS));
        assertEquals(Set.of("Hydrating"), ProductContract.group(List.of("Dryness", "Hydrating"), ProductContract.TEXTURES));
    }
}
