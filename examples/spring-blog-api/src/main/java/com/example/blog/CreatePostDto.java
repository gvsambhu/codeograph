package com.example.blog;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/**
 * DTO for creating a blog post.
 * Exercises ADR-010 Fork 7 (JSR-380 bean validation).
 */
public record CreatePostDto(

        @NotNull
        @NotBlank
        @Size(min = 3, max = 120)
        String title,

        @NotNull
        @NotBlank
        @Size(min = 10, max = 5000)
        String content,

        @NotNull
        @NotBlank
        String authorEmail
) {}
