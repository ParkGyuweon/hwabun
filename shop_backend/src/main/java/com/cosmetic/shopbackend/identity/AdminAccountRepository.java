package com.cosmetic.shopbackend.identity;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AdminAccountRepository
  extends JpaRepository<AdminAccount, String>
{
  Optional<AdminAccount> findByEmail(String email);
}
