package io.codeograph.corpus.core;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * Immutable value object for a postal address.
 * Exercises: @AllArgsConstructor + @Getter Lombok synthesis, two String fields.
 */
@AllArgsConstructor
@Getter
public class Address {

    private final String street;
    private final String city;
}
