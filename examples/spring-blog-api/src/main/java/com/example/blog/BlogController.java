package com.example.blog;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * REST controller for blog posts.
 * Exercises ADR-010 Fork 2 (HTTP routing) + Fork 9 (security policy).
 */
@RestController
@RequestMapping("/blogs")
public class BlogController {

    private final BlogService blogService;

    public BlogController(BlogService blogService) {
        this.blogService = blogService;
    }

    @GetMapping
    public List<CreatePostDto> listPosts() {
        return blogService.findAll();
    }

    @GetMapping("/{id}")
    public ResponseEntity<CreatePostDto> getPost(@PathVariable Long id) {
        return blogService.findById(id)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @PostMapping
    @PreAuthorize("hasRole('USER')")
    public ResponseEntity<CreatePostDto> createPost(@Valid @RequestBody CreatePostDto dto) {
        CreatePostDto created = blogService.create(dto);
        return ResponseEntity.status(201).body(created);
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasRole('USER')")
    public ResponseEntity<CreatePostDto> updatePost(
            @PathVariable Long id,
            @Valid @RequestBody UpdatePostDto dto) {
        return blogService.update(id, dto)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasRole('USER')")
    public ResponseEntity<Void> deletePost(@PathVariable Long id) {
        blogService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
