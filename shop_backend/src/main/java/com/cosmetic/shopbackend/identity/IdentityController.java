package com.cosmetic.shopbackend.identity;

import com.cosmetic.shopbackend.brand.Brand;
import com.cosmetic.shopbackend.brand.BrandRepository;
import com.cosmetic.shopbackend.security.JwtTokenService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.*;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
public class IdentityController {

  private final SellerAccountRepository sellers;
  private final MemberRepository members;
  private final AdminAccountRepository admins;
  private final PasswordEncoder encoder;
  private final JwtTokenService tokens;
  private final BrandRepository brands;

  public IdentityController(
    SellerAccountRepository s,
    MemberRepository m,
    AdminAccountRepository a,
    PasswordEncoder e,
    JwtTokenService t
  ) {
    this(s, m, a, e, t, null);
  }

  @Autowired
  public IdentityController(
    SellerAccountRepository s,
    MemberRepository m,
    AdminAccountRepository a,
    PasswordEncoder e,
    JwtTokenService t,
    BrandRepository b
  ) {
    sellers = s;
    members = m;
    admins = a;
    encoder = e;
    tokens = t;
    brands = b;
  }

  public record RegisterMember(
    @Email @NotBlank String email,
    @NotBlank @Size(min = 8) String password,
    @NotBlank String nickname,
    @Size(max = 32) String skinTypeCode,
    @Size(max = 32) String skinToneCode,
    @Size(max = 32) String hairColorCode,
    @Size(max = 32) String eyeColorCode
  ) {}

  public record RegisterSeller(
    @Email @NotBlank String email,
    @NotBlank @Size(min = 8) String password,
    @NotBlank String name
  ) {}

  public record Login(
    @Email @NotBlank String email,
    @NotBlank String password,
    @NotNull AccountRole role
  ) {}

  public record AccountResponse(
    String id,
    String email,
    String name,
    String role,
    String status,
    String token
  ) {}

  @PostMapping("/members")
  public ResponseEntity<AccountResponse> member(
    @Valid @RequestBody RegisterMember r
  ) {
    if (
      members.findByEmail(r.email()).isPresent()
    ) return ResponseEntity.status(HttpStatus.CONFLICT).build();
    Member m = new Member();
    m.setEmail(r.email());
    m.setNickname(r.nickname());
    m.setPasswordHash(encoder.encode(r.password()));
    m.setSkinTypeCode(r.skinTypeCode());
    m.setSkinToneCode(r.skinToneCode());
    m.setHairColorCode(r.hairColorCode());
    m.setEyeColorCode(r.eyeColorCode());
    members.save(m);
    return ResponseEntity.status(HttpStatus.CREATED).body(
      response(
        m.getId(),
        m.getEmail(),
        m.getNickname(),
        AccountRole.MEMBER,
        m.getStatus()
      )
    );
  }

  @PostMapping("/sellers")
  public ResponseEntity<AccountResponse> seller(
    @Valid @RequestBody RegisterSeller r
  ) {
    if (
      sellers.findByEmail(r.email()).isPresent()
    ) return ResponseEntity.status(HttpStatus.CONFLICT).build();
    SellerAccount s = new SellerAccount();
    s.setEmail(r.email());
    s.setName(r.name());
    s.setPasswordHash(encoder.encode(r.password()));
    sellers.save(s);
    return ResponseEntity.status(HttpStatus.CREATED).body(
      response(
        s.getId(),
        s.getEmail(),
        s.getName(),
        AccountRole.SELLER,
        s.getStatus()
      )
    );
  }

  @PostMapping("/login")
  public ResponseEntity<AccountResponse> login(@Valid @RequestBody Login r) {
    return switch (r.role()) {
      case MEMBER -> members
        .findByEmail(r.email())
        .filter(x -> authenticate(x, r.password()))
        .map(x ->
          ResponseEntity.ok(
            response(
              x.getId(),
              x.getEmail(),
              x.getNickname(),
              AccountRole.MEMBER,
              x.getStatus()
            )
          )
        )
        .orElseGet(() -> ResponseEntity.status(401).build());
      case SELLER -> sellers
        .findByEmail(r.email())
        .filter(x -> authenticate(x, r.password()))
        .map(x ->
          ResponseEntity.ok(
            response(
              x.getId(),
              x.getEmail(),
              x.getName(),
              AccountRole.SELLER,
              x.getStatus()
            )
          )
        )
        .orElseGet(() -> ResponseEntity.status(401).build());
      case ADMIN -> admins
        .findByEmail(r.email())
        .filter(x -> authenticate(x, r.password()))
        .map(x ->
          ResponseEntity.ok(
            response(
              x.getId(),
              x.getEmail(),
              x.getName(),
              AccountRole.ADMIN,
              x.getStatus()
            )
          )
        )
        .orElseGet(() -> ResponseEntity.status(401).build());
    };
  }

  private boolean authenticate(Member account, String password) {
    if (account.getStatus() != AccountStatus.ACTIVE) return false;
    return migrateOrMatch(
      account.getPasswordHash(),
      password,
      account::setPasswordHash,
      () -> members.save(account)
    );
  }

  private boolean authenticate(SellerAccount account, String password) {
    if (account.getStatus() != AccountStatus.ACTIVE) return false;
    return migrateOrMatch(
      account.getPasswordHash(),
      password,
      account::setPasswordHash,
      () -> sellers.save(account)
    );
  }

  private boolean authenticate(AdminAccount account, String password) {
    if (account.getStatus() != AccountStatus.ACTIVE) return false;
    return migrateOrMatch(
      account.getPasswordHash(),
      password,
      account::setPasswordHash,
      () -> admins.save(account)
    );
  }

  private boolean migrateOrMatch(
    String stored,
    String submitted,
    java.util.function.Consumer<String> replace,
    java.util.function.Supplier<?> persist
  ) {
    if (PasswordHashes.isLegacySha256(stored)) {
      if (!PasswordHashes.legacyMatches(stored, submitted)) return false;
      replace.accept(encoder.encode(submitted));
      persist.get();
      return true;
    }
    return encoder.matches(submitted, stored);
  }

  private AccountResponse response(
    String id,
    String email,
    String name,
    AccountRole role,
    AccountStatus status
  ) {
    String brandId = null;
    if (role == AccountRole.SELLER && brands != null) {
      brandId = brands.findAllBySeller_Id(id).stream()
        .map(Brand::getId)
        .findFirst()
        .orElse(null);
    }
    return new AccountResponse(
      id,
      email,
      name,
      role.name(),
      status.name(),
      tokens.issue(id, role, brandId)
    );
  }
}
