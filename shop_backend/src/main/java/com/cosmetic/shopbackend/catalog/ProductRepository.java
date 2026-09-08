package com.cosmetic.shopbackend.catalog;
import org.springframework.data.jpa.repository.*; import org.springframework.data.repository.query.Param; import java.math.BigDecimal; import java.util.*;
public interface ProductRepository extends JpaRepository<Product,String>{ List<Product> findByStatus(Product.Status status); List<Product> findByBrandId(String brandId); @Query("select avg(p.rating) from Product p where p.tertiaryCategory = :category and p.rating is not null") Optional<BigDecimal> averageRatingByTertiary(@Param("category") String category); }
