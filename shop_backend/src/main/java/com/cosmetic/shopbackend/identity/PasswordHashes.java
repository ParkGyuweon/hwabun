package com.cosmetic.shopbackend.identity;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.regex.Pattern;

/**
 * 저장된 비밀번호 해시 판별. 로그인(IdentityController)과 회원 탈퇴의 비밀번호 확인이 같은 규칙을 쓴다.
 *
 * 예전 시드는 SHA-256 16진수(64자)로 들어 있었고, 로그인에 성공하면 BCrypt 로 바꿔 저장한다.
 */
final class PasswordHashes {

  private static final Pattern LEGACY_SHA256 = Pattern.compile("[0-9a-fA-F]{64}");

  private PasswordHashes() {}

  static boolean isLegacySha256(String value) {
    return value != null && value.length() == 64 && LEGACY_SHA256.matcher(value).matches();
  }

  static boolean legacyMatches(String stored, String submitted) {
    return MessageDigest.isEqual(
      stored.getBytes(StandardCharsets.US_ASCII),
      legacyHash(submitted).getBytes(StandardCharsets.US_ASCII)
    );
  }

  static String legacyHash(String value) {
    try {
      return HexFormat.of().formatHex(
        MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))
      );
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
  }
}
