package com.example.validation;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import jakarta.validation.Valid;

/**
 * DTO for creating a product — exercises ADR-010 Fork 7 (JSR-380 annotation
 * translation).  Multiple constraints per field tests the "heavy" scenario.
 */
public class CreateProductRequest {

    @NotBlank(message = "Product name must not be blank")
    @Size(min = 2, max = 100, message = "Name must be between 2 and 100 characters")
    private String name;

    @NotBlank
    @Size(max = 500)
    private String description;

    @NotNull(message = "Price is required")
    @DecimalMin(value = "0.01", message = "Price must be greater than zero")
    private Double price;

    @NotNull
    @Min(value = 0, message = "Stock cannot be negative")
    @Max(value = 10000, message = "Stock cannot exceed 10000")
    private Integer stockQuantity;

    @NotBlank
    @Pattern(regexp = "^[A-Z]{2,4}-\\d{4,8}$", message = "SKU must match format XX-0000")
    private String sku;

    @NotBlank
    @Email(message = "Supplier email must be valid")
    private String supplierEmail;

    @NotNull
    @Valid
    private CategoryReference category;

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

    public CategoryReference getCategory() { return category; }
    public void setCategory(CategoryReference category) { this.category = category; }
}
