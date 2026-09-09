package com.cosmetic.shopbackend.identity;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SellerAccountRepository
  extends JpaRepository<SellerAccount, String>
{
  Optional<SellerAccount> findByEmail(String email);
}
