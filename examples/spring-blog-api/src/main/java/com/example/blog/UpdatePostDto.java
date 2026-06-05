package com.example.blog;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Size;

/**
 * DTO for updating a blog post (all fields optional — patch semantics).
 * Exercises ADR-010 Fork 7 (JSR-380 validation: @Size, @Email).
 */
public record UpdatePostDto(

        @Size(min = 3, max = 120)
        String title,

        @Size(min = 10, max = 5000)
        String content,

        @Email
        String authorEmail
) {}
