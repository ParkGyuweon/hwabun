package com.cosmetic.shopbackend.security;

import com.cosmetic.shopbackend.identity.AccountRole;

public record ShopPrincipal(String accountId, AccountRole role, String brandId) {
  public ShopPrincipal(String accountId, AccountRole role) {
    this(accountId, role, null);
  }
}
