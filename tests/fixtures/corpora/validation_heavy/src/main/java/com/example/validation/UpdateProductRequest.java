package com.example.validation;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * DTO for updating a product — all fields optional except id; exercises
 * partial-update validation patterns (ADR-010 Fork 7).
 */
public class UpdateProductRequest {

    @NotNull
    private Long id;

    @Size(min = 2, max = 100)
    private String name;

    @Size(max = 500)
    private String description;

    @DecimalMin(value = "0.01")
    private Double price;

    @Min(0)
    @Max(10000)
    private Integer stockQuantity;

    @Pattern(regexp = "^[A-Z]{2,4}-\\d{4,8}$")
    private String sku;

    @Email
    private String supplierEmail;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public Double getPrice() { return price; }
    public void setPrice(Double price) { this.price = price; }

    public Integer getStockQuantity() { return stockQuantity; }
    public void setStockQuantity(Integer stockQuantity) { this.stockQuantity = stockQuantity; }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public String getSupplierEmail() { return supplierEmail; }
    public void setSupplierEmail(String supplierEmail) { this.supplierEmail = supplierEmail; }
}
