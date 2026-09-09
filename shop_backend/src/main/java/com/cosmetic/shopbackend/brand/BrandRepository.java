package com.cosmetic.shopbackend.brand;

import java.util.*;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BrandRepository extends JpaRepository<Brand, String> {
  List<Brand> findAllBySeller_Id(String sellerId);
  Optional<Brand> findByIdAndSeller_Id(String id, String sellerId);
}
