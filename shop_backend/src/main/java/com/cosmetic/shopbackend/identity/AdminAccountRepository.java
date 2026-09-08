package com.cosmetic.shopbackend.identity;
import org.springframework.data.jpa.repository.JpaRepository; import java.util.Optional;
public interface AdminAccountRepository extends JpaRepository<AdminAccount,String>{ Optional<AdminAccount> findByEmail(String email); }
