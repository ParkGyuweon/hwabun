package com.cosmetic.shopbackend.security;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import static org.junit.jupiter.api.Assertions.*;

class PasswordEncoderTest {
    @Test
    void bcryptMatchesOriginalPasswordButNotDifferentPassword() {
        BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();

        String encoded = encoder.encode("correct horse battery staple");

        assertNotEquals("correct horse battery staple", encoded);
        assertTrue(encoder.matches("correct horse battery staple", encoded));
        assertFalse(encoder.matches("wrong password", encoded));
    }
}
