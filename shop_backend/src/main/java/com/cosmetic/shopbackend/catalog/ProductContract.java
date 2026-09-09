package com.cosmetic.shopbackend.catalog;

import java.math.*;
import java.util.*;

final class ProductContract {

  static final Set<String> CONCERNS = Set.of(
    "Dullness/Uneven Texture",
    "Dryness",
    "Anti-Aging",
    "Pores",
    "Loss of firmness",
    "Dark Circles",
    "Acne/Blemishes",
    "Redness",
    "Dark spots"
  );
  static final Set<String> CLEAN = Set.of(
    "Clean at Sephora",
    "Vegan",
    "Without Parabens",
    "Cruelty-Free",
    "Clean + Planet Positive",
    "Fragrance Free",
    "Oil Free",
    "Without Sulfates SLS & SLES",
    "Without Silicones",
    "Refill Available",
    "Without Phthalates",
    "Alcohol Free",
    "Without Mineral Oil",
    "Gluten Free",
    "Hypoallergenic",
    "Without Oxybenzone"
  );
  static final Set<String> TEXTURES = Set.of(
    "Hydrating",
    "Plumping",
    "Radiant Finish",
    "Natural Finish",
    "High Shine Finish"
  );
  static final Set<String> SECONDARY = Set.of(
    "Cleansers",
    "Eye Care",
    "Lip Balms & Treatments",
    "Masks",
    "Moisturizers",
    "Self Tanners",
    "Sunscreen",
    "Treatments"
  );
  static final Set<String> TERTIARY = Set.of(
    "BB & CC Creams",
    "Blemish & Acne Treatments",
    "Exfoliators",
    "Eye Creams & Treatments",
    "Eye Masks",
    "Face Masks",
    "Face Oils",
    "Face Serums",
    "Face Sunscreen",
    "Face Wash & Cleansers",
    "Face Wipes",
    "Facial Peels",
    "For Face",
    "Lip Balms & Treatments",
    "Makeup Removers",
    "Mists & Essences",
    "Moisturizers",
    "Night Creams",
    "Toners"
  );

  private ProductContract() {}

  static BigDecimal usd(BigDecimal krw) {
    return krw.divide(BigDecimal.valueOf(1300), 2, RoundingMode.HALF_UP);
  }

  static String priceBin(BigDecimal usd) {
    double p = usd.doubleValue();
    return p < 20
      ? "~20"
      : p < 35
        ? "20-35"
        : p < 50
          ? "35-50"
          : p < 80
            ? "50-80"
            : "80+";
  }

  static Set<String> group(Collection<String> values, Set<String> vocabulary) {
    Set<String> out = new LinkedHashSet<>();
    for (String v : values) if (vocabulary.contains(v)) out.add(v);
    return out;
  }

  static boolean isKnownHighlight(String value) {
    return (
      CONCERNS.contains(value) ||
      CLEAN.contains(value) ||
      TEXTURES.contains(value)
    );
  }

  record ProductInput(
    String productName,
    String categoryId,
    String secondaryCategory,
    String tertiaryCategory,
    List<String> highlights,
    String ingredients,
    BigDecimal priceKrw,
    String primaryImageUrl,
    String descriptionJson
  ) {}
}
