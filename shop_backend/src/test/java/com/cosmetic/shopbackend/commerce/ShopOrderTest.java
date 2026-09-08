package com.cosmetic.shopbackend.commerce;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.*;

class ShopOrderTest {
    @Test
    void newOrderStartsCreatedAndPaymentMovesItToPaid() {
        ShopOrder order = new ShopOrder("o-1", "m-1", "request-1", "hash", BigDecimal.TEN);

        assertEquals(ShopOrder.Status.CREATED, order.getStatus());
        order.paid();
        assertEquals(ShopOrder.Status.PAID, order.getStatus());
    }

    @Test
    void paymentIsIdempotentAfterFirstSuccessfulPayment() {
        ShopOrder order = new ShopOrder("o-1", "m-1", "request-1", "hash", BigDecimal.TEN);

        order.paid();
        order.paid();

        assertEquals(ShopOrder.Status.PAID, order.getStatus());
    }
}
