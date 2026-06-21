package com.example.validation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

/**
 * Nested DTO validated via {@code @Valid} on the parent request — exercises
 * the cascaded / nested validation path (ADR-010 Fork 7).
 */
public class CategoryReference {

    @NotNull
    @Positive
    private Long id;

    @NotBlank
    @Size(min = 1, max = 50)
    private String name;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
