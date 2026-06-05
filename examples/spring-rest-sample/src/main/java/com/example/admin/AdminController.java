package com.example.admin;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

/**
 * Admin endpoint — uses Spring Security @PreAuthorize.
 * Used to test the security_feature_policy = "exclude" path in the renderer.
 */
@RestController
@RequestMapping("/api/admin")
@PreAuthorize("hasRole('ADMIN')")
public class AdminController {

    @GetMapping("/stats")
    @PreAuthorize("hasAuthority('STATS_READ')")
    public String getStats() {
        return "stats";
    }

    @DeleteMapping("/purge")
    @PreAuthorize("hasRole('SUPER_ADMIN')")
    public void purge() {
        // admin action
    }
}
