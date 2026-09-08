package com.cosmetic.shopbackend.identity;

import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.*;

class RequestActorTest {
    @Test
    void trimsIdentityAndNormalizesRole() {
        RequestActor actor = RequestActor.require("  member-1  ", " member ", AccountRole.MEMBER);

        assertEquals("member-1", actor.userId());
        assertEquals(AccountRole.MEMBER, actor.role());
    }

    @Test
    void rejectsMissingHeadersAsUnauthorized() {
        ResponseStatusException error = assertThrows(ResponseStatusException.class,
                () -> RequestActor.require("member-1", "", AccountRole.MEMBER));

        assertEquals(401, error.getStatusCode().value());
    }

    @Test
    void rejectsUnknownRoleAsUnauthorized() {
        ResponseStatusException error = assertThrows(ResponseStatusException.class,
                () -> RequestActor.require("member-1", "ROOT", AccountRole.ADMIN));

        assertEquals(401, error.getStatusCode().value());
    }

    @Test
    void rejectsValidButDisallowedRoleAsForbidden() {
        ResponseStatusException error = assertThrows(ResponseStatusException.class,
                () -> RequestActor.require("member-1", "MEMBER", AccountRole.SELLER));

        assertEquals(403, error.getStatusCode().value());
    }
}
