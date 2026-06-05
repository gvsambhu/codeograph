package com.example.orders;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import java.math.BigDecimal;

public record OrderDto(
        Long id,

        @NotBlank(message = "Customer name must not be blank")
        String customerName,

        @NotNull @Positive(message = "Total amount must be positive")
        BigDecimal totalAmount
) {}
