package io.codeograph.corpus.web;

/**
 * Marker interface for endpoints that expose their API version.
 * Exercises: interface node, default method (non-abstract), no fields.
 */
public interface Versioned {

    /** Return the API version string (e.g. "v1"). */
    default String apiVersion() {
        return "v1";
    }
}
