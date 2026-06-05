package com.example.blog;

import com.querydsl.core.types.Predicate;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * JPA repository for Post entities.
 * Exercises ADR-010 Fork 4 (db_layer JPA + QueryDSL raw_sql path).
 */
@Repository
public interface PostRepository extends JpaRepository<Post, Long>,
        QuerydslPredicateExecutor<Post> {

    List<Post> findByAuthorEmail(String authorEmail);

    @Query("SELECT p FROM Post p WHERE p.title LIKE %:keyword% OR p.content LIKE %:keyword%")
    List<Post> searchByKeyword(@Param("keyword") String keyword);
}
