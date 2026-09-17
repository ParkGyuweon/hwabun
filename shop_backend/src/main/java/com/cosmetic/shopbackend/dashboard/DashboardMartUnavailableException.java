package com.cosmetic.shopbackend.dashboard;

public class DashboardMartUnavailableException extends RuntimeException {
  private final String mart;

  public DashboardMartUnavailableException(String mart) {
    this.mart = mart;
  }

  public String mart() {
    return mart;
  }
}
