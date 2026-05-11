package io.codeograph.corpus.core;

import lombok.Value;

/**
 * Immutable pagination parameters.
 * Exercises: @Value (all-fields constructor + getters, no setters), primitive int fields.
 */
@Value
public class PageRequest {

    int page;
    int size;

    /** Guard: page index must not be negative. */
    public void validate() {
        if (page < 0) {
            throw new IllegalArgumentException("page must be >= 0");
        }
        if (size <= 0) {
            throw new IllegalArgumentException("size must be > 0");
        }
    }
}
