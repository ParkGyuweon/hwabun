package com.cosmetic.shopbackend.identity;

import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.util.Arrays;

/** Temporary request identity contract until Spring Security/JWT is introduced. */
public record RequestActor(String userId, AccountRole role) {
    public static RequestActor require(String userIdHeader, String roleHeader, AccountRole... allowedRoles) {
        if (userIdHeader == null || userIdHeader.isBlank() || roleHeader == null || roleHeader.isBlank()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "authentication headers required");
        }
        final AccountRole role;
        try {
            role = AccountRole.valueOf(roleHeader.trim().toUpperCase());
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "invalid account role");
        }
        if (allowedRoles == null || allowedRoles.length == 0 || Arrays.stream(allowedRoles).noneMatch(role::equals)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "insufficient account role");
        }
        return new RequestActor(userIdHeader.trim(), role);
    }
}
