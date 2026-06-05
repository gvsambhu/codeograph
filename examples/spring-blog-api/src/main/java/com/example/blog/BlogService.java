package com.example.blog;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

/**
 * Service layer for blog posts.
 * Exercises ADR-010 Fork 1 (DI) + Fork 3 (transactions).
 */
@Service
@Transactional(readOnly = true)
public class BlogService {

    private final PostRepository postRepository;

    public BlogService(PostRepository postRepository) {
        this.postRepository = postRepository;
    }

    public List<CreatePostDto> findAll() {
        return postRepository.findAll()
                .stream()
                .map(this::toDto)
                .toList();
    }

    public Optional<CreatePostDto> findById(Long id) {
        return postRepository.findById(id).map(this::toDto);
    }

    @Transactional
    public CreatePostDto create(CreatePostDto dto) {
        Post post = new Post();
        post.setTitle(dto.title());
        post.setContent(dto.content());
        post.setAuthorEmail(dto.authorEmail());
        Post saved = postRepository.save(post);
        return toDto(saved);
    }

    @Transactional
    public Optional<CreatePostDto> update(Long id, UpdatePostDto dto) {
        return postRepository.findById(id).map(post -> {
            if (dto.title() != null) post.setTitle(dto.title());
            if (dto.content() != null) post.setContent(dto.content());
            return toDto(postRepository.save(post));
        });
    }

    @Transactional
    public void delete(Long id) {
        postRepository.deleteById(id);
    }

    private CreatePostDto toDto(Post post) {
        return new CreatePostDto(post.getTitle(), post.getContent(), post.getAuthorEmail());
    }
}
