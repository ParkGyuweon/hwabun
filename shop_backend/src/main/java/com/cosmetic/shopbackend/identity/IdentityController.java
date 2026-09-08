package com.cosmetic.shopbackend.identity;

import jakarta.validation.Valid; import jakarta.validation.constraints.*; import org.springframework.http.*; import org.springframework.web.bind.annotation.*;
import com.cosmetic.shopbackend.security.JwtTokenService;
import org.springframework.security.crypto.password.PasswordEncoder;
import java.nio.charset.StandardCharsets; import java.security.MessageDigest; import java.util.*;

@RestController @RequestMapping("/api/auth")
public class IdentityController {
 private final SellerAccountRepository sellers; private final MemberRepository members; private final AdminAccountRepository admins; private final PasswordEncoder encoder; private final JwtTokenService tokens;
 public IdentityController(SellerAccountRepository s, MemberRepository m, AdminAccountRepository a, PasswordEncoder e, JwtTokenService t){sellers=s;members=m;admins=a;encoder=e;tokens=t;}
 public record RegisterMember(@Email @NotBlank String email,@NotBlank @Size(min=8) String password,@NotBlank String nickname){}
 public record RegisterSeller(@Email @NotBlank String email,@NotBlank @Size(min=8) String password,@NotBlank String name){}
 public record Login(@Email @NotBlank String email,@NotBlank String password, @NotNull AccountRole role){}
 public record AccountResponse(String id,String email,String name,String role,String status,String token){}
 @PostMapping("/members") public ResponseEntity<AccountResponse> member(@Valid @RequestBody RegisterMember r){ if(members.findByEmail(r.email()).isPresent()) return ResponseEntity.status(HttpStatus.CONFLICT).build(); Member m=new Member();m.setEmail(r.email());m.setNickname(r.nickname());m.setPasswordHash(encoder.encode(r.password()));members.save(m);return ResponseEntity.status(HttpStatus.CREATED).body(response(m.getId(),m.getEmail(),m.getNickname(),AccountRole.MEMBER,m.getStatus())); }
 @PostMapping("/sellers") public ResponseEntity<AccountResponse> seller(@Valid @RequestBody RegisterSeller r){ if(sellers.findByEmail(r.email()).isPresent()) return ResponseEntity.status(HttpStatus.CONFLICT).build(); SellerAccount s=new SellerAccount();s.setEmail(r.email());s.setName(r.name());s.setPasswordHash(encoder.encode(r.password()));sellers.save(s);return ResponseEntity.status(HttpStatus.CREATED).body(response(s.getId(),s.getEmail(),s.getName(),AccountRole.SELLER,s.getStatus())); }
 @PostMapping("/login") public ResponseEntity<AccountResponse> login(@Valid @RequestBody Login r){ return switch(r.role()){case MEMBER->members.findByEmail(r.email()).filter(x->x.getStatus()==AccountStatus.ACTIVE&&encoder.matches(r.password(),x.getPasswordHash())).map(x->ResponseEntity.ok(response(x.getId(),x.getEmail(),x.getNickname(),AccountRole.MEMBER,x.getStatus()))).orElseGet(()->ResponseEntity.status(401).build());case SELLER->sellers.findByEmail(r.email()).filter(x->x.getStatus()==AccountStatus.ACTIVE&&encoder.matches(r.password(),x.getPasswordHash())).map(x->ResponseEntity.ok(response(x.getId(),x.getEmail(),x.getName(),AccountRole.SELLER,x.getStatus()))).orElseGet(()->ResponseEntity.status(401).build());case ADMIN->admins.findByEmail(r.email()).filter(x->x.getStatus()==AccountStatus.ACTIVE&&encoder.matches(r.password(),x.getPasswordHash())).map(x->ResponseEntity.ok(response(x.getId(),x.getEmail(),x.getName(),AccountRole.ADMIN,x.getStatus()))).orElseGet(()->ResponseEntity.status(401).build());}; }
 private AccountResponse response(String id,String email,String name,AccountRole role,AccountStatus status){return new AccountResponse(id,email,name,role.name(),status.name(),tokens.issue(id,role));}
}
