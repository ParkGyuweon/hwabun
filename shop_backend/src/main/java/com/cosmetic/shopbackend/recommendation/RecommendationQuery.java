package com.cosmetic.shopbackend.recommendation;

import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** Client-controlled portion of the recommendation request. */
public record RecommendationQuery(
  int size,
  int reserved,
  int bannerSlots,
  String axes,
  String hero,
  String skinType,
  String skinTone,
  String hairColor,
  String eyeColor
) {

  private static final Set<String> ALLOWED_AXES = Set.of(
    "concern", "ingredient", "clean", "price_bin", "category", "segment"
  );
  private static final String DEFAULT_AXES = "concern,segment";

  public RecommendationQuery {
    if (size < 1 || size > 50) invalid("size must be between 1 and 50");
    if (reserved < 0 || reserved > 10) invalid("reserved must be between 0 and 10");
    if (bannerSlots < 0 || bannerSlots > 12) invalid("banner_slots must be between 0 and 12");
    axes = Arrays.stream((axes == null ? "" : axes).split(","))
      .map(String::trim)
      .filter(axis -> !axis.isEmpty())
      .collect(Collectors.joining(","));
    if (axes.isEmpty()) axes = DEFAULT_AXES;
    boolean invalidAxis = Arrays.stream(axes.split(","))
      .anyMatch(axis -> !ALLOWED_AXES.contains(axis));
    if (invalidAxis) invalid("axes contains an unsupported value");
    hero = blankToNull(hero);
    if (hero == null) hero = "top";
    skinType = blankToNull(skinType);
    skinTone = blankToNull(skinTone);
    hairColor = blankToNull(hairColor);
    eyeColor = blankToNull(eyeColor);
  }

  private static String blankToNull(String value) {
    return value == null || value.isBlank() ? null : value;
  }

  private static void invalid(String message) {
    throw new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
  }
}
