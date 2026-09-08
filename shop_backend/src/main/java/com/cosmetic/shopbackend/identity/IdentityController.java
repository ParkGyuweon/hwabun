package com.cosmetic.shopbackend.identity;

import jakarta.validation.Valid; import jakarta.validation.constraints.*; import org.springframework.http.*; import org.springframework.web.bind.annotation.*;
import java.nio.charset.StandardCharsets; import java.security.MessageDigest; import java.util.*;

@RestController @RequestMapping("/api/auth")
public class IdentityController {
 private final SellerAccountRepository sellers; private final MemberRepository members; private final AdminAccountRepository admins;
 public IdentityController(SellerAccountRepository s, MemberRepository m, AdminAccountRepository a){sellers=s;members=m;admins=a;}
 public record RegisterMember(@Email @NotBlank String email,@NotBlank @Size(min=8) String password,@NotBlank String nickname){}
 public record RegisterSeller(@Email @NotBlank String email,@NotBlank @Size(min=8) String password,@NotBlank String name){}
 public record Login(@Email @NotBlank String email,@NotBlank String password, @NotNull AccountRole role){}
 public record AccountResponse(String id,String email,String name,String role,String status){}
 @PostMapping("/members") public ResponseEntity<AccountResponse> member(@Valid @RequestBody RegisterMember r){ if(members.findByEmail(r.email()).isPresent()) return ResponseEntity.status(HttpStatus.CONFLICT).build(); Member m=new Member();m.setEmail(r.email());m.setNickname(r.nickname());m.setPasswordHash(hash(r.password()));members.save(m);return ResponseEntity.status(HttpStatus.CREATED).body(new AccountResponse(m.getId(),m.getEmail(),m.getNickname(),"MEMBER",m.getStatus().name())); }
 @PostMapping("/sellers") public ResponseEntity<AccountResponse> seller(@Valid @RequestBody RegisterSeller r){ if(sellers.findByEmail(r.email()).isPresent()) return ResponseEntity.status(HttpStatus.CONFLICT).build(); SellerAccount s=new SellerAccount();s.setEmail(r.email());s.setName(r.name());s.setPasswordHash(hash(r.password()));sellers.save(s);return ResponseEntity.status(HttpStatus.CREATED).body(new AccountResponse(s.getId(),s.getEmail(),s.getName(),"SELLER",s.getStatus().name())); }
 @PostMapping("/login") public ResponseEntity<AccountResponse> login(@Valid @RequestBody Login r){ return switch(r.role()){case MEMBER->members.findByEmail(r.email()).filter(x->x.getStatus()==AccountStatus.ACTIVE && x.getPasswordHash().equals(hash(r.password()))).map(x->ResponseEntity.ok(new AccountResponse(x.getId(),x.getEmail(),x.getNickname(),"MEMBER",x.getStatus().name()))).orElseGet(()->ResponseEntity.status(401).build());case SELLER->sellers.findByEmail(r.email()).filter(x->x.getStatus()==AccountStatus.ACTIVE && x.getPasswordHash().equals(hash(r.password()))).map(x->ResponseEntity.ok(new AccountResponse(x.getId(),x.getEmail(),x.getName(),"SELLER",x.getStatus().name()))).orElseGet(()->ResponseEntity.status(401).build());case ADMIN->admins.findByEmail(r.email()).filter(x->x.getStatus()==AccountStatus.ACTIVE && x.getPasswordHash().equals(hash(r.password()))).map(x->ResponseEntity.ok(new AccountResponse(x.getId(),x.getEmail(),x.getName(),"ADMIN",x.getStatus().name()))).orElseGet(()->ResponseEntity.status(401).build());}; }
 static String hash(String value){try{byte[] b=MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));return HexFormat.of().formatHex(b);}catch(Exception e){throw new IllegalStateException(e);}}
}
