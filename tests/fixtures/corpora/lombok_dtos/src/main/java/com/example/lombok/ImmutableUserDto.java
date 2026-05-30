package com.example.lombok;

import lombok.Value;

@Value
public class ImmutableUserDto {
    Long id;
    String username;
    String email;
}
