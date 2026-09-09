package com.cosmetic.shopbackend.catalog;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductUnmappedValueRepository
  extends JpaRepository<ProductUnmappedValue, String> {}
