package com.example.lombok;

import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

@Slf4j
@Service
@AllArgsConstructor
public class UserService {
    private final Object someDependency;

    public void doSomething(UserDto user) {
        log.info("Processing user: {}", user.getUsername());
    }
}
