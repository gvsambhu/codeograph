package io.codeograph.corpus.core;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import lombok.Builder;
import lombok.Data;

import java.util.UUID;

/**
 * Core domain entity representing a customer order.
 *
 * Exercises:
 *   - @Data (getters, setters, RequiredArgsConstructor, equals, hashCode, toString synthesis)
 *   - @Builder (static builder() entry point)
 *   - Bean validation constraints (@NotBlank, @NotNull, @Positive)
 *   - implements Displayable (interface relationship edge)
 *   - One explicit method (display) alongside synthesised methods
 */
@Data
@Builder
public class Order implements Displayable {

    @NotNull
    private final UUID id;

    @NotBlank
    private final String customerId;

    @NotNull
    private OrderStatus status;

    @Positive
    private double totalAmount;

    private Address shippingAddress;

    @Override
    public String display() {
        return "Order[" + id + ", " + status + ", $" + totalAmount + "]";
    }

    /** Transition the order to the next lifecycle state. */
    public void advance() {
        if (status == OrderStatus.PENDING) {
            status = OrderStatus.CONFIRMED;
        } else if (status == OrderStatus.CONFIRMED) {
            status = OrderStatus.SHIPPED;
        }
    }
}
