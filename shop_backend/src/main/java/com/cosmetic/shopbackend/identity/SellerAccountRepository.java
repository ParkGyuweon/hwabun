package com.cosmetic.shopbackend.identity;
import org.springframework.data.jpa.repository.JpaRepository; import java.util.Optional;
public interface SellerAccountRepository extends JpaRepository<SellerAccount,String>{ Optional<SellerAccount> findByEmail(String email); }
