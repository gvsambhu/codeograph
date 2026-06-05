package com.example.blog;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * Typed configuration properties for the blog module.
 * Exercises ADR-010 Fork 6 (ConfigurationProperties).
 */
@ConfigurationProperties(prefix = "blog")
@Validated
public class BlogConfig {

    @NotBlank
    private String title = "My Blog";

    @Min(1)
    private int maxPostsPerPage = 20;

    @Min(0)
    private int maxFeaturedPosts = 5;

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public int getMaxPostsPerPage() {
        return maxPostsPerPage;
    }

    public void setMaxPostsPerPage(int maxPostsPerPage) {
        this.maxPostsPerPage = maxPostsPerPage;
    }

    public int getMaxFeaturedPosts() {
        return maxFeaturedPosts;
    }

    public void setMaxFeaturedPosts(int maxFeaturedPosts) {
        this.maxFeaturedPosts = maxFeaturedPosts;
    }
}
