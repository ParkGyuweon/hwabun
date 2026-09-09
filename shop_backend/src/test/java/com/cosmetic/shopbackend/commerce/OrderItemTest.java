package com.cosmetic.shopbackend.commerce;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderItemTest {

  @Test
  void snapshotComputesLineAmountFromServerSideUnitPriceAndQuantity() {
    OrderItem item = new OrderItem(
      "i-1",
      "o-1",
      "v-1",
      "p-1",
      "b-1",
      "Product",
      "Brand",
      "SKU",
      "Shade",
      BigDecimal.valueOf(12500),
      3
    );

    // The field is persisted as line_amount; this verifies the constructor's invariant
    // without requiring a live MySQL database.
    try {
      var lineAmount = OrderItem.class.getDeclaredField("lineAmount");
      lineAmount.setAccessible(true);
      assertEquals(BigDecimal.valueOf(37500), lineAmount.get(item));
    } catch (ReflectiveOperationException e) {
      throw new AssertionError(e);
    }
  }
}
