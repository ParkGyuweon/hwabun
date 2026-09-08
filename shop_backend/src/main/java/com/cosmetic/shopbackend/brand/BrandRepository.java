package com.cosmetic.shopbackend.brand;
import org.springframework.data.jpa.repository.JpaRepository; import java.util.*;
public interface BrandRepository extends JpaRepository<Brand,String>{ List<Brand> findAllBySeller_Id(String sellerId); Optional<Brand> findByIdAndSeller_Id(String id,String sellerId); }
