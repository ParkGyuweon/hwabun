package com.cosmetic.shopbackend.catalog;
import com.cosmetic.shopbackend.brand.BrandRepository;
import org.springframework.http.*; import org.springframework.web.bind.annotation.*; import java.math.BigDecimal; import java.util.*;
@RestController @RequestMapping("/api/products")
public class CatalogController {
 private final ProductRepository products; private final ProductVariantRepository variants; private final BrandRepository brands;
 public CatalogController(ProductRepository p,ProductVariantRepository v,BrandRepository b){products=p;variants=v;brands=b;}
 @GetMapping public List<Product> list(){return products.findByStatus(Product.Status.ACTIVE);}
 @GetMapping("/{id}") public ResponseEntity<?> get(@PathVariable String id){return products.findById(id).filter(p->p.getStatus()==Product.Status.ACTIVE).map(p->Map.of("product",p,"variants",variants.findByProductId(id).stream().filter(v->v.getStatus()==ProductVariant.Status.ACTIVE).toList())).map(ResponseEntity::ok).orElseGet(()->ResponseEntity.notFound().build());}
 public record ProductRequest(String brandId,String categoryId,String name,String primaryImageUrl){}
 @PostMapping public ResponseEntity<Product> create(@RequestHeader(value="X-User-Id",required=false) String seller,@RequestHeader(value="X-User-Role",required=false) String role,@RequestBody ProductRequest r){
  if(!"SELLER".equalsIgnoreCase(role)||seller==null||r.brandId()==null||r.brandId().isBlank()||r.categoryId()==null||r.categoryId().isBlank()||r.name()==null||r.name().isBlank()||brands.findByIdAndSeller_Id(r.brandId(),seller).isEmpty()) return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
  Product p=new Product(UUID.randomUUID().toString(),r.brandId(),r.categoryId(),r.name()); p.update(r.name(),r.categoryId(),r.primaryImageUrl()); return ResponseEntity.status(HttpStatus.CREATED).body(products.save(p)); }
 @PutMapping("/{id}") public ResponseEntity<?> update(@RequestHeader(value="X-User-Id",required=false) String seller,@RequestHeader(value="X-User-Role",required=false) String role,@PathVariable String id,@RequestBody ProductRequest r){return products.findById(id).filter(p->"SELLER".equalsIgnoreCase(role)&&brands.findByIdAndSeller_Id(p.getBrandId(),seller).isPresent()).map(p->{p.update(r.name(),r.categoryId(),r.primaryImageUrl());return ResponseEntity.ok(products.save(p));}).orElseGet(()->ResponseEntity.status(HttpStatus.FORBIDDEN).build());}
 @PatchMapping("/{id}/status") public ResponseEntity<?> status(@RequestHeader(value="X-User-Id",required=false) String seller,@RequestHeader(value="X-User-Role",required=false) String role,@PathVariable String id,@RequestParam Product.Status value){return products.findById(id).filter(p->"SELLER".equalsIgnoreCase(role)&&brands.findByIdAndSeller_Id(p.getBrandId(),seller).isPresent()).map(p->{p.status(value);return ResponseEntity.ok(products.save(p));}).orElseGet(()->ResponseEntity.status(HttpStatus.FORBIDDEN).build());}
}
