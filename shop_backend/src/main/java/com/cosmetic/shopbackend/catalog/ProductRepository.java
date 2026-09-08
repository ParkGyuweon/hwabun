package com.cosmetic.shopbackend.catalog;
import org.springframework.data.jpa.repository.*; import java.util.*;
public interface ProductRepository extends JpaRepository<Product,String>{ List<Product> findByStatus(Product.Status status); List<Product> findByBrandId(String brandId); }
