package com.cosmetic.shopbackend.catalog;

import java.util.*;
import org.springframework.data.jpa.repository.*;

public interface ProductVariantRepository
  extends JpaRepository<ProductVariant, String>
{
  List<ProductVariant> findByProductId(String productId);
  Optional<ProductVariant> findFirstByProductIdAndLabel(
    String productId,
    String label
  );
}
