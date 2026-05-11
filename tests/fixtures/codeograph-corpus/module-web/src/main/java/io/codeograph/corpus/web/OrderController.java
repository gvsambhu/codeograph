package io.codeograph.corpus.web;

import io.codeograph.corpus.core.Order;
import io.codeograph.corpus.core.OrderService;
import io.codeograph.corpus.core.PageRequest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

/**
 * REST controller for the /orders resource.
 *
 * Exercises:
 *   - @RestController stereotype
 *   - @RequestMapping at class level
 *   - @Autowired field injection (AutowiresEdge to OrderService)
 *   - implements Versioned (interface relationship)
 *   - @GetMapping, @PostMapping HTTP verbs
 *   - cross-module dependency: io.codeograph.corpus.core.* (DependsOnEdge)
 */
@RestController
@RequestMapping("/orders")
public class OrderController implements Versioned {

    @Autowired
    private OrderService orderService;

    @GetMapping("/{customerId}")
    public ResponseEntity<List<Order>> listOrders(
            @PathVariable String customerId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        List<Order> orders = orderService.listOrders(customerId, new PageRequest(page, size));
        return ResponseEntity.ok(orders);
    }

    @PostMapping
    public ResponseEntity<Order> placeOrder(@RequestBody PlaceOrderRequest req) {
        Order created = orderService.placeOrder(req.customerId(), req.amount(), null);
        return ResponseEntity.ok(created);
    }

    @PostMapping("/{orderId}/cancel")
    public ResponseEntity<Void> cancelOrder(@PathVariable UUID orderId) {
        boolean cancelled = orderService.cancel(orderId);
        if (cancelled) {
            return ResponseEntity.noContent().build();
        }
        return ResponseEntity.badRequest().build();
    }

    record PlaceOrderRequest(String customerId, double amount) {}
}
