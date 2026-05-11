package io.codeograph.corpus.core;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * Application service coordinating order lifecycle operations.
 *
 * Exercises:
 *   - @Service stereotype
 *   - @Autowired field injection (AutowiresEdge to repository)
 *   - cyclomatic complexity > 1 (if/else branches in placeOrder, cancel)
 *   - cross-method calls within the same class (LCOM4 cohesion)
 *   - return-type references to Order, OrderStatus, PageRequest (DependsOnEdge)
 */
@Service
public class OrderService {

    @Autowired
    private OrderRepository orderRepository;

    /**
     * Create and persist a new order.
     * Complexity: 2 (one branch — null address guard).
     */
    public Order placeOrder(String customerId, double amount, Address shippingAddress) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId must not be blank");
        }
        Order order = Order.builder()
                .id(UUID.randomUUID())
                .customerId(customerId)
                .status(OrderStatus.PENDING)
                .totalAmount(amount)
                .shippingAddress(shippingAddress)
                .build();
        return save(order);
    }

    /** Retrieve a page of orders for a customer. */
    public List<Order> listOrders(String customerId, PageRequest page) {
        return orderRepository.findByCustomerId(customerId, page.getPage(), page.getSize());
    }

    /**
     * Cancel an order if it is still cancellable.
     * Complexity: 3 (two branches — status checks).
     */
    public boolean cancel(UUID orderId) {
        Optional<Order> opt = orderRepository.findById(orderId);
        if (opt.isEmpty()) {
            return false;
        }
        Order order = opt.get();
        if (order.getStatus() == OrderStatus.SHIPPED) {
            return false;
        }
        order.setStatus(OrderStatus.CANCELLED);
        save(order);
        return true;
    }

    private Order save(Order order) {
        return orderRepository.save(order);
    }
}
