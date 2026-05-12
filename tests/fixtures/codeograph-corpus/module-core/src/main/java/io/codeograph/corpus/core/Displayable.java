package io.codeograph.corpus.core;

/**
 * Marker interface for domain objects that can produce a human-readable label.
 * Exercises: interface node, single abstract method, no fields.
 */
public interface Displayable {

    /** Return a short human-readable label for this object. */
    String display();
}
