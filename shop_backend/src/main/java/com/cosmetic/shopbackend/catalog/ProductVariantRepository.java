package com.cosmetic.shopbackend.catalog;
import org.springframework.data.jpa.repository.*; import java.util.*;
public interface ProductVariantRepository extends JpaRepository<ProductVariant,String>{ List<ProductVariant> findByProductId(String productId); Optional<ProductVariant> findFirstByProductIdAndLabel(String productId,String label); }
