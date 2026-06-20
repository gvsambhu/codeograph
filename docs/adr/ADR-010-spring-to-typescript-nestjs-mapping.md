---
status: accepted
date: 2026-05-26
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-010 — Spring Boot to NestJS/TypeScript Idiom Mapping

## Context and Problem Statement

The pluggable renderer interface (ADR-008) and selection layer (ADR-009) decide *how* renderers plug in and *which* classes get rendered. This ADR decides *what* the v1 TypeScript/NestJS renderer actually does — the per-feature translation rules from Spring Boot 3 source to idiomatic NestJS 10.x output.

A faithful Spring → NestJS translation is genuinely tractable because the two ecosystems share a decorator-based, constructor-injected mental model. The interesting design work is not "should we use decorators" but the per-feature mapping decisions: how Spring's HATEOAS wrappers translate, how QueryDSL custom repositories survive when no clean TypeORM analogue exists, how `@ControllerAdvice` global handlers become NestJS exception filters, how `@ConfigurationProperties` survive as typed config classes, and which Spring features are honestly out of v1 scope.

The translation must produce output that:
1. Runs out of the box (`npm install && npm run start:dev`) for the default configuration — preview value depends on the output being inspectable end-to-end, not just compile-checkable.
2. Reads as idiomatic NestJS to a reviewer who knows the framework — not as transliterated Java.
3. Preserves enough of the source structure that a reviewer can compare Spring source against TypeScript output side by side and trust the translation.
4. Is honest about what it could not translate — every gap surfaces as a reviewable TODO comment or a refuse-to-render decision, not a silent drop.
5. Fails loudly on dangerous omissions — Spring Security configs missing from output would ship an open endpoint where the source had an authenticated one; this category gets refuse-to-render by default.

The decisions cover nine concerns: dependency injection, HTTP routing, HATEOAS hypermedia, persistence (and `@Transactional`), exception handling, configuration and properties, DTOs and Bean Validation, render granularity (and Lombok), and the consolidated Spring feature coverage matrix with encounter-behavior policy.

## Decision Drivers

* **Industry-standard pattern / reviewer recognition** — output matches what a NestJS engineer would write by hand for the same Spring class.
* **Least surprise** — a Java/Spring veteran reading the TypeScript output recognizes their own code.
* **Realistic enterprise targets** — every locked mapping handles the patterns actually present in production Spring Boot 3 codebases (JPA, QueryDSL, Spring Data Audit, Lombok, `@Valid`, `@ControllerAdvice`).
* **No silent failures** — features that cannot be translated faithfully become reviewable TODOs or refuse-to-render entries; never silent drops.
* **YAGNI** — Spring Cloud, Spring Batch, Spring Integration, messaging, AOP, Boot Actuator, custom `BeanPostProcessor`, and reactive WebFlux are explicitly out of v1.
* **Forward compatibility with v1.1** — every v1.1-deferred feature has a stub or TODO placeholder in v1 output that a future renderer amendment can replace.
* **LLM budget preservation** — per-class render granularity maximizes cache reuse; one class change invalidates one cache entry.
* **Determinism / determinism boundary clarity** — the decorator-mapping tables and the strategy ladders are deterministic; LLM judgment is confined to translating the class body once the mapping rules have been applied.
* **Readability as a curated artefact** — the consolidated feature coverage matrix is the source of truth for what v1 translates and the bridge to the project's honest disclosure list.

## Considered Options

### Fork 1 — Dependency Injection translation

* **(a) faithful 1:1 — `@Service`/`@Repository`/`@Component` → `@Injectable()`; constructor injection with `private readonly`; per-feature `<domain>.module.ts` files generated; stereotype-preservation JSDoc; `@Qualifier` → `@Inject('TOKEN')` local transformation; `@Scope`/`@Lazy` deferred to Fork 9. ✅**
* (b) minimal decorators — plain classes with manual `useClass` provider registration in every module.
* (c) property-based DI mirroring Spring field injection (`@Inject() private foo!: Foo`).
* (d) hybrid by complexity — simple services use (a); services with `@Qualifier`/factory beans use explicit `useFactory`.

### Fork 2 — HTTP layer translation

* (a) strict 1:1 faithful — `@RestController` → `@Controller`, `@GetMapping` → `@Get()`, etc.; edge cases (`ResponseEntity<T>`, `HttpServletRequest`, content negotiation) left to LLM judgment.
* **(b) strict 1:1 + explicit edge-case translation rule table covering `ResponseEntity` stripping, `HttpServletRequest`/`Response` escape hatches, content negotiation, method-overload handling, and global CORS via `enableCors()` in `main.ts`. ✅**
* (c) per-endpoint controller — one class per endpoint.
* (d) hybrid split — large controllers split by sub-resource path pattern.

### Fork 3 — HATEOAS handling

* (a) drop HATEOAS entirely; always plain JSON output.
* (b) reuse the legacy three-mode configurable (`self`/`full`/`none`).
* **(c) auto-detect Spring HATEOAS usage in source; strip `EntityModel`/`CollectionModel`/`PagedModel` wrappers; add `Page<T>` interface to scaffold; per-method TODO with original link configuration text preserved for manual restoration. ✅**
* (d) auto-detect + emit minimal `buildSelfLink(req)` helper where source had `_links`.

### Fork 4 — Persistence (and `@Transactional`)

* **(a) TypeORM two-tier — `Repository<Entity>` for standard CRUD; raw SQL via `DataSource.query()` for QueryDSL/Blaze custom impls; `@Transactional` translated as `dataSource.transaction(async (manager) => {...})` callback wrapper. Configurable via `db_layer: typeorm_2tier (default) | typeorm_only | raw_only`. ✅**
* (b) TypeORM all-in — translate even QueryDSL/Blaze to TypeORM QueryBuilder.
* (c) Prisma — schema-first ORM.
* (d) typed interfaces + raw SQL only (no ORM).
* (e) configurable — `db_layer` with all four modes (Prisma kept).

### Fork 5 — Exception translation

* **(a) throw NestJS `HttpException` subclasses; per-exception mapping table; `@ControllerAdvice` → generated global `@Catch`-decorated `ExceptionFilter`; custom Spring exceptions translated as `extends HttpException`. ✅**
* (b) services throw plain `Error` subclasses; a central filter translates every domain error to its HTTP response.
* (c) `Result<T, E>` functional pattern via `neverthrow` or `ts-results`.
* (d) hybrid — services throw plain `Error`; controllers `try/catch` and rethrow as `HttpException`.

### Fork 6 — Configuration and properties

* (a) minimal — `application.yml` → `.env`; `@Value("${prop}")` → `configService.get<string>('PROP')`; everything as string lookups.
* (b) full typed — every `@Value` and every `@ConfigurationProperties` resolves to a typed config class with `class-validator` at startup.
* (c) YAML mirror — keep the YAML file format; use a YAML loader for `@nestjs/config`.
* **(d) hybrid — `@ConfigurationProperties` → typed config classes with `class-validator` validation at startup; `application.yml` flattened to `.env.example`; `@Value` → typed `configService.get('PROP', { infer: true })`; `@Configuration` + `@Bean` → `useFactory` providers; `@Profile` → module-level `NODE_ENV`-conditional imports. ✅**

### Fork 7 — DTO and Bean Validation

* **(a) class-based DTOs + `class-validator` decorators + global `ValidationPipe` in `main.ts` scaffold; per-decorator mapping table; `@Valid` cascade → `@ValidateNested() + @Type(() => Nested)`; Java records → plain class with `public readonly` fields; custom `ConstraintValidator` → TS skeleton + TODO. ✅**
* (b) interface-only DTOs — no runtime validation.
* (c) zod schemas — modern alternative with type inference.
* (d) class-based DTOs with per-endpoint `@UsePipes(ValidationPipe)` instead of global.

### Fork 8 — Render granularity (and Lombok)

* **(a) per-class — one Java class becomes one LLM call becomes one output `.ts` file; Lombok intent-mapping (`@Data` → plain class, `@Value` → readonly, `@Slf4j` → NestJS `Logger`, etc.); `render_strategy: Literal["per_class"]` forward-pointer for future per-domain mode. ✅**
* (b) per-file — one Java file becomes one LLM call (handles multi-class files together).
* (c) per-domain — one LLM call covers all classes in a domain.
* (d) per-class default + interface field for future per-domain.

Lombok sub-strategy: (A.1) translate source-as-written with the Lombok annotations as comments, (A.2) translate the AST-synthesized form with explicit getters/setters/`equals`/`hashCode`, **(A.3) translate annotation intent to the idiomatic TS analogue per a Lombok mapping table ✅**.

### Fork 9 — Spring feature coverage matrix and encounter behavior

* (X) TODO comment + skip (silent rendering without the feature).
* (Y) stub + TODO (render a no-op stub with the original intent commented).
* (Z) refuse to render the affected class (fail loud).
* **(W) hybrid — stub + TODO for most categories; refuse-to-render for Security categories; refuse WebFlux entirely. Configurable via `unsupported_feature_policy`, `security_feature_policy`, `webflux_policy` fields with default-recommended-policy semantics; CLI presets `--strict-features` and `--permissive-features` for coherent combinations. ✅**

## Decision Outcome

### Fork 1 — DI translation: (a) faithful 1:1 with module wiring and stereotype JSDoc

Spring's `@Service`, `@Repository`, `@Component`, `@Controller`, and `@RestController` all collapse to NestJS `@Injectable()` (controllers keep `@Controller`). Constructor injection uses `private readonly` parameters — the modern Spring 4.3+ best practice translates directly to the NestJS-idiomatic pattern. Every translated class carries a JSDoc trailer naming the source FQCN and stereotype so reviewers can trace the translation.

```typescript
/**
 * Translated from com.example.users.UserService (@Service)
 */
@Injectable()
export class UsersService {
  constructor(
    private readonly userRepo: UserRepository,
    private readonly mailer: MailerService,
  ) {}
  // ...
}
```

**Per-feature module wiring** closes the legacy gap of users hand-writing `<domain>.module.ts` files. For each domain emitted by ADR-009's selector, the renderer also emits one module file:

```typescript
// users/users.module.ts
@Module({
  controllers: [UsersController],
  providers:   [UsersService, UserRepository],
  exports:     [UsersService],
})
export class UsersModule {}
```

The scaffold's `src/app.module.ts.j2` template imports all generated per-feature modules so `npm run start:dev` works out of the box.

**`@Qualifier` and disambiguation.** `@Qualifier("primaryDataSource") DataSource ds` becomes `@Inject('PRIMARY_DATA_SOURCE') private ds: DataSource` in the consumer plus a `{ provide: 'PRIMARY_DATA_SOURCE', useClass: PrimaryDataSource }` entry in the providing module — a local transformation, not a separate fork.

**`@Scope` (request/prototype) and `@Lazy`** are deferred to Fork 9 (stub + TODO) — they are rare and the NestJS analogues (`Scope.REQUEST`, custom factory providers) require careful integration not justified in v1.

### Fork 2 — HTTP layer: (b) strict 1:1 with explicit edge-case rule table

Spring MVC and NestJS HTTP routing are conceptually 1:1; the design work is in the edge cases Spring exposes that do not translate cleanly. The renderer prompt encodes a deterministic rule table so the LLM does not hallucinate when source uses `ResponseEntity`, escape-hatch parameters, or content negotiation:

| Spring pattern | NestJS translation |
|---|---|
| `@RestController` | `@Controller` |
| `@GetMapping`/`@PostMapping`/`@PutMapping`/`@DeleteMapping`/`@PatchMapping` | `@Get()`/`@Post()`/`@Put()`/`@Delete()`/`@Patch()` |
| `@PathVariable` | `@Param()` |
| `@RequestBody` | `@Body()` |
| `@RequestParam` | `@Query()` |
| `@RequestHeader` | `@Headers()` |
| `ResponseEntity<T>` body return | Return `T` directly; if non-default status, add `@HttpCode(HttpStatus.<NAME>)` |
| `ResponseEntity.status(s).header(k, v).body(b)` (dynamic headers) | `@Res({ passthrough: true })` with TODO if logic is complex; `@Header(k, v)` for static headers |
| `HttpServletRequest req` | `@Req() req: Request` (from `express`); add `import { Request } from 'express'` |
| `HttpServletResponse resp` | `@Res({ passthrough: true }) res: Response`; comment notes NestJS recommendation against direct response use |
| `@CrossOrigin` on controller/method | Skip per-method; `main.ts` scaffold enables `app.enableCors()` globally with config note |
| `produces = "application/json"` | Skip (NestJS default) |
| `produces` non-default | `@Header('Content-Type', '<value>')` + comment |
| `@RequestMapping` (no HTTP method specified) | Emit `// TODO: Spring @RequestMapping accepts all verbs; specify @Get/@Post/etc.` and skip method body translation |
| Method overloads on same path | Render the first variant; emit `// TODO: source had method overloads on this path; manually handle additional content types` |
| `@PathVariable(value="id", required=true)` | `@Param('id')` — pipe-based validation is Fork 7 territory |

**Global CORS in `main.ts`** rather than per-method `@CrossOrigin` matches NestJS norms and keeps the cross-cutting concern in one place. Spring projects almost always have one CORS policy.

### Fork 3 — HATEOAS: (c) auto-detect + wrapper strip + `Page<T>` + TODO with original link text

The renderer detects Spring HATEOAS in source via imports of `org.springframework.hateoas.*`. When detected:
- `EntityModel<X>` returns are stripped → return `X` directly.
- `CollectionModel<X>` returns are stripped → return `X[]`.
- `PagedModel<X>` returns translate to a typed `Page<X>` shape (added to scaffold as `src/common/types/page.interface.ts.j2`).

For each affected method the renderer emits a TODO comment containing the *original* link configuration text from source so the reviewer has everything needed to restore links manually:

```typescript
@Get(':id')
get(@Param('id') id: string): Promise<User> {
  // TODO: source had:
  //   EntityModel.of(u, linkTo(methodOn(UserController.class).get(id)).withSelfRel(),
  //                     linkTo(methodOn(OrderController.class).byUser(id)).withRel("orders"))
  //   _links dropped in v1 translation; restore with manual link builders if needed.
  return this.users.findOne(id);
}
```

When source has no HATEOAS imports, nothing extra appears in output — clean handling for the realistic majority of projects that do not depend on Spring HATEOAS.

The `Page<T>` interface (added to the scaffold) is useful even for non-HATEOAS pagination via Spring Data's `Page<T>` and `Pageable`:

```typescript
export interface Page<T> {
  items: T[];
  page: number;
  size: number;
  totalElements: number;
}
```

### Fork 4 — Persistence and `@Transactional`: (a) TypeORM 2-tier, callback `@Transactional`, configurable via `db_layer`

**Default mode (`db_layer: typeorm_2tier`):** standard JPA repositories (`extends JpaRepository<T, ID>`) become TypeORM `Repository<T>` accessed via `@InjectRepository(T)`. Custom QueryDSL or Blaze Persistence implementations become raw-SQL repositories using `DataSource.query()` with parameterized queries. Tier routing is deterministic from the source class structure — no LLM judgment.

```typescript
// users.entity.ts
@Entity({ name: 'users' })
export class User {
  @PrimaryGeneratedColumn() id!: number;
  @Column({ unique: true }) email!: string;
  @ManyToOne(() => Org, org => org.users) org!: Org;
}

// users.repository.ts — Tier A (TypeORM)
@Injectable()
export class UsersRepository {
  constructor(@InjectRepository(User) private readonly repo: Repository<User>) {}
  // derived query methods translate to repo.findOne({ where: {...} })
}

// custom-users.repository.ts — Tier B (raw SQL)
@Injectable()
export class CustomUsersRepository {
  constructor(private readonly dataSource: DataSource) {}

  async findActiveByOrgWithWindow(orgId: number): Promise<UserStatRow[]> {
    // TODO: source used Blaze Persistence entity view; converted to raw SQL
    const rows = await this.dataSource.query(`
      SELECT u.id, u.email,
             ROW_NUMBER() OVER (PARTITION BY u.org_id ORDER BY u.created_at) AS rank
      FROM users u
      WHERE u.org_id = $1 AND u.active = true
    `, [orgId]);
    return rows.map(r => ({ id: r.id, email: r.email, rank: Number(r.rank) }));
  }
}
```

**Configurability via `TypeScriptConfig.db_layer`:**

| Mode | Behavior |
|---|---|
| `typeorm_2tier` (default) | TypeORM for standard CRUD; raw SQL for QueryDSL/Blaze custom impls. |
| `typeorm_only` | All repositories via TypeORM `Repository<T>` or `createQueryBuilder()`. QueryDSL/Blaze methods get attempted QueryBuilder translation with `// TODO: source used <pattern>; verify equivalence` comments. Accepts fidelity loss on complex queries. |
| `raw_only` | No ORM. Every repository becomes `@Injectable()` with `private readonly ds: DataSource`; every method is `await this.ds.query('...', [params])`. Entity classes stripped of `@Entity` decorators and emitted as typed interfaces only. |

Prisma was rejected as a configurable mode because schema-first ORMs are architecturally incompatible with Fork 8's per-class render granularity.

**`@Transactional` translation** is the same across all `db_layer` modes — the callback wrapper:

```typescript
async createUserAndOrg(req: CreateRequest): Promise<User> {
  return this.dataSource.transaction(async (manager) => {
    const org  = await manager.save(Org,  { name: req.orgName });
    const user = await manager.save(User, { email: req.email, org });
    return user;
  });
}
```

The `typeorm-transactional` library decorator was considered but rejected — adding a community-maintained external dependency to every generated project is real vouch surface. The callback wrapper is verbose but native and explicit.

**Persistence sub-rules table** (applied by the renderer prompt):

| Sub-question | Decision |
|---|---|
| `JpaRepository<User, Long>` extension | `users.repository.ts` with `@InjectRepository(User) private repo: Repository<User>`; no separate interface |
| Derived query methods (`findByEmail`, `findByOrgIdAndActiveTrue`) | TypeORM `repo.findOne({ where: {...} })` — name-to-criteria translation rules in prompt |
| `@Query("SELECT u FROM User u WHERE ...")` (JPQL) | TypeORM QueryBuilder when straightforward; raw SQL fallback otherwise + TODO |
| `@Query(nativeQuery = true)` | Raw SQL via `DataSource.query()` with parameterization |
| `Page<T>` / `Pageable` | Use the `Page<T>` interface from Fork 3; manual `skip` + `take` + `count()` |
| `Specification<T>` (dynamic queries) | Raw SQL fallback + TODO (no clean TypeORM analogue) |
| Spring Data Audit (`@CreatedDate`, `@LastModifiedDate`) | TypeORM `@CreateDateColumn`, `@UpdateDateColumn` |
| `@Transactional(propagation = REQUIRES_NEW)` etc. | TODO comment (TypeORM does not natively support propagation modes) |
| `@EntityListeners` | TODO (no clean analogue) |
| DTO projections (interface or constructor) | Explicit `select` + DTO interface; TODO if complex |

### Fork 5 — Exception translation: (a) `HttpException` subclasses + generated `ExceptionFilter`

Per-exception mapping table (applied by the renderer prompt):

| Spring exception | NestJS translation |
|---|---|
| `IllegalArgumentException` | `BadRequestException` |
| `EntityNotFoundException`, `NoSuchElementException` | `NotFoundException` |
| `AccessDeniedException` | `ForbiddenException` |
| `AuthenticationException` | `UnauthorizedException` |
| `DataIntegrityViolationException`, `DuplicateKeyException` | `ConflictException` |
| `UnsupportedOperationException` | `MethodNotAllowedException` |
| `IllegalStateException` | `InternalServerErrorException` |
| `RuntimeException` (generic) | `InternalServerErrorException` + `Logger.error(...)` |
| `ResponseStatusException(HttpStatus.X, msg)` | `new HttpException(msg, HttpStatus.X)` |
| Custom `extends RuntimeException` with `@ResponseStatus(HttpStatus.X)` | Custom class extends `HttpException` with status baked in |
| Custom `extends RuntimeException` (no `@ResponseStatus`) | Custom class extends `HttpException` with `HttpStatus.INTERNAL_SERVER_ERROR` + TODO to verify intended status |

**`@ControllerAdvice` translation** generates a NestJS `ExceptionFilter` per `@ExceptionHandler` method:

```typescript
// common/filters/user-not-found-exception.filter.ts
@Catch(UserNotFoundException)
export class UserNotFoundExceptionFilter implements ExceptionFilter {
  catch(exception: UserNotFoundException, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<Response>();
    response.status(404).json({ message: exception.message });
  }
}
```

The scaffold's `main.ts` template registers all generated filters via `app.useGlobalFilters(...)`.

**Exception sub-rules:**

| Sub-question | Decision |
|---|---|
| `try/catch` blocks in source | Translate 1:1; `catch (e: Error)` typed parameter; re-throw if no specific handling |
| `throw new Exception("msg", cause)` (cause chain) | `new HttpException("msg", status, { cause })` (Node 16.9+) |
| Spring's default error response shape | Accept NestJS default in v1; emit `// TODO: error response shape differs from Spring default` in `main.ts` if `@ControllerAdvice` was translated |
| Exception with `@ResponseStatus` on the *class* | Custom class extends `HttpException` with that status baked in; no per-throw status needed |
| `HandlerMethodArgumentResolver` failures (validation errors) | Routed through Fork 7's `ValidationPipe` → `BadRequestException` |
| Unchecked vs checked exceptions | TS has no checked exceptions; all `throws` clauses dropped |
| Stack trace preservation | Default TS behavior via the `cause` chain |
| Logging from `@ExceptionHandler` | `log.error(...)` calls → `Logger.error(...)` (NestJS Logger) |

A service-layer error-translation alternative (services throw plain `Error`; a single filter maps to HTTP) was considered as a Fork 5 retrofit candidate but deferred to a future ADR amendment — the moderate scaffold overhead (a `DomainError` base, a `DomainErrorFilter`, a per-project error-to-status registry) is not justified until a real user requests HTTP-agnostic services.

### Fork 6 — Configuration and properties: (d) typed `@ConfigurationProperties` + flat `.env` + `useFactory`

**`@ConfigurationProperties(prefix="datasource")`** translates to a typed config class with `class-validator` validation, materialized at startup via a `useFactory` provider:

```typescript
// src/config/datasource.config.ts
@Injectable()
export class DatasourceConfig {
  @IsUrl() url!: string;
  @IsString() username!: string;
  @IsString() password!: string;
  @IsInt() @Min(1) maxPoolSize!: number;
}

// src/config/datasource-config.module.ts (one per @ConfigurationProperties class)
@Module({
  providers: [
    {
      provide: DatasourceConfig,
      useFactory: (cs: ConfigService) => {
        const cfg = plainToInstance(DatasourceConfig, {
          url: cs.get('DATASOURCE_URL'),
          username: cs.get('DATASOURCE_USERNAME'),
          password: cs.get('DATASOURCE_PASSWORD'),
          maxPoolSize: Number(cs.get('DATASOURCE_MAX_POOL_SIZE', '10')),
        });
        const errors = validateSync(cfg);
        if (errors.length) throw new Error(`Invalid DATASOURCE config: ${errors}`);
        return cfg;
      },
      inject: [ConfigService],
    },
  ],
  exports: [DatasourceConfig],
})
export class DatasourceConfigModule {}

// consumer
@Injectable()
export class UsersRepository {
  constructor(private readonly ds: DatasourceConfig) {}  // typed, validated
}
```

**`@Value("${db.url}")`** that is *not* grouped under any `@ConfigurationProperties` becomes a typed lookup at the call site:

```typescript
const url = this.configService.get('DATABASE_URL', { infer: true });
// + TODO comment nudging the user to group these under @ConfigurationProperties
```

**`@Configuration` + `@Bean` methods** translate to NestJS `useFactory` custom providers in a generated module. Simple beans (single return value with property injection) translate mechanically; complex bean methods (conditional branches, multi-step setup) emit `// TODO:` with the original Java code preserved as comment for manual porting.

**`@Profile("dev")`** translates to module-level `NODE_ENV` conditional imports:

```typescript
@Module({
  imports: [
    process.env.NODE_ENV === 'dev' ? DevModule : ProdModule,
    // ...
  ],
})
```

Per-bean `@Profile` conditionals (rare in practice) emit `// TODO:` with the original profile expression.

**`application.yml` → `.env.example`.** Nested YAML keys flatten to upper-snake-case ENV names with `_` separator (`spring.datasource.url` → `SPRING_DATASOURCE_URL`; `logging.level.root` → `LOGGING_LEVEL_ROOT`). Profile-specific overrides (`application-dev.yml`) produce `.env.development` and a comment documenting precedence.

**Scaffold additions for configuration:**

| Template | Purpose |
|---|---|
| `.env.example.j2` | Auto-populated from detected Spring properties |
| `src/config/configuration.module.ts.j2` | Root `ConfigModule.forRoot()` setup with env validation |

Per-`@ConfigurationProperties` typed config classes are LLM-generated from source (not from templates) — the structure is project-specific.

**`@RefreshScope`** is deferred to Fork 9 (stub + TODO) — live config reload requires a different runtime architecture.

### Fork 7 — DTO and Bean Validation: (a) class-based DTOs + global `ValidationPipe`

Java DTOs (POJOs, records, Lombok `@Value`/`@Data` classes) become TypeScript classes annotated with `class-validator` decorators. The scaffold's `main.ts` registers a single global `ValidationPipe({ whitelist: true, transform: true, forbidNonWhitelisted: true })` so every controller endpoint with `@Body()` gets validation without per-endpoint pipe registration.

```typescript
// users/dto/create-user.dto.ts
export class CreateUserDto {
  @IsNotEmpty()
  @IsEmail()
  email!: string;

  @IsString()
  @MinLength(8)
  @MaxLength(72)
  password!: string;

  @IsOptional()
  @IsInt()
  @Min(0)
  @Max(150)
  age?: number;

  @ValidateNested()
  @Type(() => AddressDto)
  address!: AddressDto;
}
```

**Per-decorator mapping table:**

| Spring (JSR-380 / Hibernate) | NestJS (class-validator) |
|---|---|
| `@NotNull` | `@IsDefined()` (or `@IsNotEmpty()` for strings; context-dependent) |
| `@NotEmpty` (string) | `@IsNotEmpty()` |
| `@NotEmpty` (collection) | `@ArrayNotEmpty()` |
| `@NotBlank` | `@IsNotEmpty()` + `@IsString()` |
| `@Size(min, max)` (string) | `@MinLength(min) @MaxLength(max)` |
| `@Size(min, max)` (collection) | `@ArrayMinSize(min) @ArrayMaxSize(max)` |
| `@Email` | `@IsEmail()` |
| `@Pattern(regexp="...")` | `@Matches(/.../)` |
| `@Min` / `@Max` | `@Min` / `@Max` |
| `@DecimalMin` / `@DecimalMax` | `@Min` / `@Max` (numeric coercion) |
| `@Positive` / `@Negative` | `@IsPositive()` / `@IsNegative()` |
| `@PositiveOrZero` / `@NegativeOrZero` | `@Min(0)` / `@Max(0)` |
| `@Past` / `@Future` | `@IsDate()` + custom validator (TODO comment — no direct analogue) |
| `@Digits(integer, fraction)` | `@IsNumberString({ ... })` + `@Matches(/.../)` |
| `@AssertTrue` / `@AssertFalse` | Custom validator (TODO) |
| `@Null` | `@IsEmpty()` |
| `@Valid` (cascade) | `@ValidateNested() @Type(() => NestedDto)` |
| `@URL` (Hibernate) | `@IsUrl()` |
| `@CreditCard` (Hibernate) | `@IsCreditCard()` |
| `@Range(min, max)` (Hibernate) | `@Min(min) @Max(max)` |

**Java records** translate to plain classes with `public readonly` fields and an all-args constructor — the closest match to a Java record's immutability + accessibility semantics.

**Custom `ConstraintValidator`** classes generate a TypeScript skeleton with the original FQCN preserved in a TODO for manual logic porting:

```typescript
@ValidatorConstraint({ name: 'isValidUserAge', async: false })
export class IsValidUserAgeConstraint implements ValidatorConstraintInterface {
  validate(value: any, args: ValidationArguments): boolean {
    // TODO: port logic from com.example.users.validators.UserAgeValidator
    return false;
  }
}
```

**Validation sub-rules:**

| Sub-question | Decision |
|---|---|
| `ValidationPipe` config | `{ whitelist: true, transform: true, forbidNonWhitelisted: true }` — strict by default (rejects unknown fields) |
| `@JsonProperty` / `@JsonIgnore` (Jackson) | `@Expose()` / `@Exclude()` from `class-transformer` |
| `@JsonFormat(pattern="yyyy-MM-dd")` | `@Type(() => Date)` + `@IsDate()` + comment if pattern is non-ISO |
| Optional fields | `@IsOptional()` BEFORE other decorators (class-validator order requirement) |
| Lombok `@Value` (immutable DTO) | Same as records — class with `public readonly` |
| Lombok `@Data` (mutable POJO) | Plain class with public fields |
| Spring's validation group inheritance | TODO comment; class-validator groups do not compose the same way |
| `BindingResult` parameter | Drop the parameter; `ValidationPipe` handles globally; comment if source manually inspected `BindingResult` |
| `@PathVariable` + `@Min`/`@Max` validation | `@Param('id', ParseIntPipe) id: number` for type coercion; TODO for range checks on path params |

### Fork 8 — Render granularity (and Lombok): (a) per-class + (A.3) Lombok intent-mapping

**Per-class granularity.** One Java class becomes one LLM call and one TypeScript output file. The renderer's concurrency (locked at 5 per ADR-008 Fork 5) parallelizes the per-class calls. Cross-class coherence is solved by the LLM prompt containing the relevant signatures and `unresolved_call` edges from the graph — the controller's prompt lists "calls `UserService.findById(Long): User`" without needing the service's full source.

**Lombok intent-mapping table:**

| Lombok annotation | TS analogue |
|---|---|
| `@Data` (mutable POJO) | Plain class with public mutable fields; constructor; no `toString`/`equals`/`hashCode` synthesis |
| `@Value` (immutable) | Class with `public readonly` fields and an all-args constructor |
| `@Getter` / `@Setter` | Public fields (TypeScript does not idiomatically use accessors for simple property access) |
| `@AllArgsConstructor` | TS constructor with all-args (NestJS DI compatible) |
| `@RequiredArgsConstructor` | TS constructor with non-null / non-default fields |
| `@NoArgsConstructor` | Default no-args constructor |
| `@Slf4j` (and variants) | `private readonly logger = new Logger(ClassName.name)` from `@nestjs/common` |
| `@SneakyThrows` | Drop the annotation; TS has no checked exceptions |
| `@Builder` | Static `builder()` method returning a fluent partial-builder (Fork 9: v1.1 candidate; basic shape only in v1) |
| `@With` | Skip; TODO (immutable-with semantics rare in NestJS code) |

**Render granularity sub-rules:**

| Sub-question | Decision |
|---|---|
| Top-level public class | Translated as its own output file |
| Top-level package-private class in same file | Co-translated into same output file (TS allows multiple non-exported classes per file); `// Note: kept package-private equivalent` comment |
| Static nested classes | Co-translated as separate `class` declarations in the parent's output file |
| Anonymous inner classes (used as callbacks) | Inline as arrow functions or lambdas where possible; TODO if complex |
| Inner classes used as data carriers | Translated as separate exported types in the same file |
| Enums | TS `enum` (1:1) |
| Interfaces | TS `interface` (1:1); if only one impl and it is a `@Service`, consider translating the impl directly (deferred to prompt design) |

**`render_strategy: Literal["per_class"]`** is added to `TypeScriptConfig` as a forward-pointer; v1.1 may expand to `Literal["per_class", "per_domain"]` for projects where cross-class coherence outweighs cache reuse — non-breaking.

### Fork 9 — Spring feature coverage matrix and encounter behavior: (W) configurable hybrid

**Encounter-behavior policy fields** on `TypeScriptConfig`:

```python
unsupported_feature_policy: Literal[
    "stub_todo",      # default — render stub + TODO comment preserving original intent
    "silent_skip",    # render without the feature, no TODO (most permissive)
    "refuse",         # refuse to render the affected class (most strict)
] = "stub_todo"

security_feature_policy: Literal[
    "stub_todo",      # render endpoint WITHOUT auth + TODO (insecure — explicit opt-in)
    "silent_skip",    # render endpoint WITHOUT auth, no TODO (most dangerous)
    "refuse",         # default — refuse to render security-affected classes
] = "refuse"

webflux_policy: Literal[
    "refuse",                # default — refuse any WebFlux class
    "translate_mono_only",   # translate Mono<T> → Promise<T>; refuse Flux<T> classes
    "best_effort",           # translate Mono → Promise, Flux → Observable<T> (RxJS) with TODOs
] = "refuse"
```

**CLI presets** map to coherent combinations:

| Preset | Combination |
|---|---|
| (none — default) | `unsupported_feature_policy=stub_todo`, `security_feature_policy=refuse`, `webflux_policy=refuse` |
| `--strict-features` | `unsupported_feature_policy=refuse`, `security_feature_policy=refuse`, `webflux_policy=refuse` |
| `--permissive-features` | `unsupported_feature_policy=stub_todo`, `security_feature_policy=stub_todo`, `webflux_policy=best_effort` — emits a loud start-of-run warning: "Permissive mode — output is NOT production-ready without manual review." |

Direct config-file overrides allow finer-grained tuning (e.g., `unsupported_feature_policy=stub_todo` AND `webflux_policy=refuse`).

**The Spring feature coverage matrix.** This is the source of truth for what v1 translates, what is deferred to v1.1 (and how it surfaces under default policy), and what is refused. The matrix is also the bridge to the project's honest disclosure documentation.

| Category | v1 (translated) | v1.1 (deferred → stub + TODO) | Out-of-scope (refuse) |
|---|---|---|---|
| **Stereotypes + DI** (Fork 1) | `@Service`, `@Repository`, `@Component`, `@Controller`, `@RestController`, `@Autowired`, constructor injection, `@Qualifier`, `@Inject` | `@Scope` (request/prototype), `@Lazy`, `@Profile` (per-bean conditionals only — module-level in Fork 6) | — |
| **HTTP routing** (Fork 2) | `@RequestMapping`, all `@*Mapping`, `@PathVariable`, `@RequestParam`, `@RequestBody`, `@RequestHeader`, `@ResponseStatus`, `@HttpCode`, global `@CrossOrigin`, `ResponseEntity<T>`, `HttpServletRequest`/`HttpServletResponse` (escape hatch) | `@RequestMapping` (no HTTP verb specified), method overloads on same path, content negotiation (`produces`/`consumes`), `@SessionAttribute`, `@MatrixVariable` | — |
| **HATEOAS** (Fork 3) | Wrapper stripping (`EntityModel`/`CollectionModel`/`PagedModel`); `Page<T>` scaffold type; per-method TODO with original link config | Full `_links` translation, `RepresentationModelAssembler` | — |
| **Persistence** (Fork 4) | JPA `@Entity`/`@Id`/`@Column`/`@OneToMany`/`@ManyToOne`/etc., `JpaRepository<T, ID>`, derived query methods, `@Query` (JPQL → QueryBuilder, raw SQL fallback), `@Query(nativeQuery=true)`, custom QueryDSL/Blaze → raw SQL tier, `@Transactional` (callback wrapper), Spring Data Audit, `Page<T>`/`Pageable` | `Specification<T>` (dynamic queries), `@EntityListeners`, `@Transactional(propagation = REQUIRES_NEW)`, JPA cascade types, MapStruct mappers | — |
| **Exceptions** (Fork 5) | Standard exception mapping table; `@ControllerAdvice` → generated `ExceptionFilter`; custom exceptions extending `HttpException` | `@ResponseStatus` on exception class (translate but with TODO); exception cause chains with deep nesting | — |
| **Configuration** (Fork 6) | `@ConfigurationProperties` → typed config class; `@Value` → typed `ConfigService.get`; `application.yml` → `.env.example` + typed classes; `@Configuration`/`@Bean` → `useFactory`; `@Profile` (module-level); `@PropertySource` | `@RefreshScope` (live reload); per-bean `@Profile` conditionals; `Environment` API direct usage with complex predicates | — |
| **DTO + Validation** (Fork 7) | Per-decorator mapping table; `@Valid` cascade → `@ValidateNested() + @Type`; Java records → readonly classes; Lombok `@Data`/`@Value`/`@AllArgsConstructor`/`@Slf4j` | Custom `ConstraintValidator` (TS skeleton + TODO); validation group inheritance; Lombok `@Builder`; Lombok `@With` | — |
| **Lombok** (Fork 8) | `@Data`, `@Value`, `@Getter`/`@Setter`, `@AllArgsConstructor`, `@RequiredArgsConstructor`, `@NoArgsConstructor`, `@Slf4j`, `@SneakyThrows` | `@Builder` (basic), `@With` | — |
| **Async / Scheduling / Events** | — | `@Async` → BullMQ / queue patterns; `@Scheduled` → `@nestjs/schedule` `@Cron`; `@EventListener` → `@nestjs/event-emitter` `@OnEvent`; `@TransactionalEventListener` | — |
| **Caching** | — | `@Cacheable` / `@CachePut` / `@CacheEvict` → `@nestjs/cache-manager` interceptors | — |
| **Security** | — | All of it — `@PreAuthorize` / `@Secured` / `SecurityFilterChain` / `@EnableWebSecurity` / JWT configs / OAuth2; refuse-to-render by default under `security_feature_policy=refuse` | — |
| **AOP** | — | `@Aspect` / `@Before` / `@After` / `@Around` → NestJS Interceptors; custom annotation + aspect pairs | — |
| **Filters / Interceptors** | — | `HandlerInterceptor`, `Filter`, `OncePerRequestFilter` → NestJS Middleware / Interceptors / Guards | — |
| **File upload** | — | `MultipartFile`, `@RequestPart`, multi-part upload | — |
| **Lifecycle** | — | `@PostConstruct` → `OnModuleInit`; `@PreDestroy` → `OnModuleDestroy` | — |
| **i18n** | — | `MessageSource`, `LocaleResolver`, `@MessageMapping` | — |
| **Boot Actuator** | — | `/actuator/health` → `@nestjs/terminus`; `/actuator/metrics` — no direct analogue | — |
| **Tests** | — | `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, `@MockBean` → Jest + `@nestjs/testing` (`Test.createTestingModule`) | — |
| **WebFlux** | — | — | All `Mono<T>`/`Flux<T>`/`WebClient` usage — refuse-to-render under `webflux_policy=refuse` |
| **Spring Cloud** | — | — | Config Server, Eureka, Gateway, OpenFeign |
| **Spring Batch** | — | — | Entire Batch framework |
| **Spring Integration** | — | — | EIP DSL |
| **Spring AMQP / JMS / Kafka** | — | — | `@RabbitListener`, `@KafkaListener`, `@JmsListener` |
| **Spring Native / GraalVM** | — | — | Compile-time AOT — fundamentally different runtime |
| **Spring Boot DevTools** | — | — | Hot-reload tooling — not applicable in NestJS context |
| **Custom Boot starters** | — | — | Conditional autoconfiguration — too project-specific |
| **`@ComponentScan` custom packages** | — | — | NestJS modules are explicit; no scan; TODO if non-default `@ComponentScan` |
| **Custom `BeanPostProcessor` / `BeanFactoryPostProcessor`** | — | — | Container customization at this level has no clean analogue |

**Audit and observability.** Each run emits the active policies and the refused/stubbed counts both in logs and in the manifest:

```
[INFO] Feature policies: unsupported=stub_todo  security=refuse  webflux=refuse
[INFO] Refused 2 classes: UserAdminController (security), OrderEventStream (webflux)
[INFO] Stub+TODO injected at 14 sites across 7 classes (see manifest.json)
```

ADR-009's `SelectionResult` is extended with `refused: dict[str, str]`, `stub_todos: dict[str, list[str]]`, and `feature_policies_active: dict[str, str]` so the audit appears alongside the selection audit.

**Encounter-behavior sub-rules:**

| Sub-question | Decision |
|---|---|
| Stub format consistency | All stubs use `// TODO: Spring <FEATURE>; <reason>. <suggested-translation>.` — same prefix everywhere; greppable |
| Encountered annotation not in matrix | Emit `// TODO: Unrecognized Spring annotation @Foo — manual translation needed.` Add to v1.1 backlog |
| Class entirely refused | Add to `SelectionResult.refused` (class_id → reason) so manifest and scorecard surface it cleanly |
| Out-of-scope detection precedence | WebFlux first (`reactor.core.publisher.*` import) → refuse-to-render the file. Spring Cloud / Batch / Integration imports → refuse-to-render with category-specific message |

### Consolidated `TypeScriptConfig`

```python
# codeograph/renderers/typescript_nestjs/config.py
from pydantic import BaseModel, ConfigDict
from typing import Literal


class TypeScriptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # --- Fork 4 (persistence) ---
    db_layer: Literal["typeorm_2tier", "typeorm_only", "raw_only"] = "typeorm_2tier"

    # --- Fork 8 (granularity) ---
    render_strategy: Literal["per_class"] = "per_class"   # v1.1 may add "per_domain"

    # --- Fork 9 (encounter behavior) ---
    unsupported_feature_policy: Literal["stub_todo", "silent_skip", "refuse"] = "stub_todo"
    security_feature_policy:    Literal["stub_todo", "silent_skip", "refuse"] = "refuse"
    webflux_policy:             Literal["refuse", "translate_mono_only", "best_effort"] = "refuse"

    # --- Scaffold (ADR-008 Fork 4) ---
    include_scaffold: bool = True
    strict:           bool = True
```

### Scaffold templates committed in this round

| Template path | Purpose |
|---|---|
| `templates/package.json.j2` | NestJS 10.x deps; `class-validator`, `class-transformer`, `@nestjs/config`, `typeorm`, driver per `db_layer` |
| `templates/tsconfig.json.j2` | TS strict mode config |
| `templates/nest-cli.json.j2` | NestJS CLI build config |
| `templates/.gitignore.j2` | Standard NestJS gitignore |
| `templates/.env.example.j2` | Auto-populated from detected Spring properties |
| `templates/src/main.ts.j2` | Bootstrap with `enableCors()`, global `ValidationPipe`, `useGlobalFilters(...)` |
| `templates/src/app.module.ts.j2` | Root module importing all generated per-feature modules |
| `templates/src/config/configuration.module.ts.j2` | Root `ConfigModule.forRoot()` setup |
| `templates/src/common/types/page.interface.ts.j2` | `Page<T>` interface for HATEOAS + `Pageable` |

### Constraint flagged for ADR-008

The consolidated `TypeScriptConfig` shape defined here is the concrete `Renderer[TypeScriptConfig]` binding that ADR-008's generic parameter expected. The `include_scaffold` and `strict` fields live on this config per ADR-008 Fork 4's scaffold opt-out commitment.

### Constraint flagged for ADR-009

`SelectionResult` is extended with three new fields (`refused`, `stub_todos`, `feature_policies_active`) so the encounter-behavior audit from Fork 9 surfaces alongside the selection audit. The class set the renderer is asked to translate may be smaller than `SelectionResult.selected` because classes refused under `security_feature_policy=refuse` or `webflux_policy=refuse` move from `selected` to `refused`.

### Constraint flagged for ADR-011 (Spring → Go mapping, v1.1)

The same nine-fork structure (DI / HTTP / persistence / exceptions / config / validation / granularity / coverage matrix / encounter behavior) applies when the Go renderer is designed. The Go renderer's idiom mapping is reserved for that future ADR; this ADR's scaffold-template pattern (`go.mod.j2`, `main.go.j2`) is the only piece that is target-agnostic.

## Consequences

**Positive.**
1. The output runs end-to-end on the default configuration (`npm install && npm run start:dev`) thanks to the scaffold from ADR-008 Fork 4 plus the per-feature module wiring from Fork 1 plus the global `ValidationPipe` and `ExceptionFilter` registration from Forks 7 and 5.
2. The coverage matrix gives reviewers a single page to check whether any given Spring feature is expected to translate, surface as a TODO, or refuse-to-render.
3. The encounter-behavior policy fields (Fork 9) and the persistence configurability (Fork 4) honor the project posture that recommended defaults plus opt-in alternatives serve more users than a single hard-coded choice.
4. Security-affected classes refuse-to-render by default — the most dangerous category of silent translation failure (open endpoint where the source had an authenticated one) becomes impossible without the user explicitly opting in via `--permissive-features` or `security_feature_policy=stub_todo`.
5. Per-class render granularity (Fork 8) maximizes cache reuse — incremental source changes invalidate one cache entry, not a whole domain.
6. Per-decorator and per-feature mapping tables are prompt-table content the LLM can apply deterministically; LLM judgment is confined to translating the class body once the rules have been applied.

**Negative.**
1. Nine forks plus the consolidated config plus the scaffold inventory plus the coverage matrix make ADR-010 the largest single ADR in the catalogue — contributors orienting in the renderer must read more before producing their first change.
2. The default `security_feature_policy=refuse` produces zero output on security-heavy projects until the user takes deliberate action. The friction is intentional but real.
3. `db_layer=typeorm_only` and `db_layer=raw_only` modes need separate prompt rule blocks; implementation cost is real (~2–4 hr each for prompt-rule additions) even though they share the `@Transactional` callback wrapper.
4. The per-class granularity decision means a controller's prompt does not see its called service's source directly — coherence depends on the prompt carrying `unresolved_call` edges and signatures from the graph. Real-world quality depends on the prompt design getting this right.
5. The coverage matrix's v1.1 row is long. Honest disclosure is the point, but it surfaces many features the tool does not fully handle in v1.
6. WebFlux `webflux_policy=refuse` defaults to skipping entire files for reactive projects. The decision is correct (best-effort reactive translation produces subtly broken code), but it is a hard limit on which Spring projects v1 can preview.

## Confirmation

1. Rendering a fixture containing a `@RestController` with `@GetMapping`, `@PostMapping`, a `@PathVariable`, a `@RequestBody`, and an injected `@Service` produces a TypeScript controller using `@Controller`, `@Get()`, `@Post()`, `@Param()`, `@Body()`, and constructor-injected service — verified by a per-decorator fixture test against the per-decorator mapping table.
2. Rendering a domain containing a controller, a service, and a repository produces three source files plus one `<domain>.module.ts` file whose `controllers`, `providers`, and `exports` arrays reference the generated classes (verified by an integration test).
3. Rendering a class with `@Transactional` on a method produces output that wraps the method body in `await this.dataSource.transaction(async (manager) => { ... })` (verified by a fixture test).
4. Rendering a fixture whose entity uses Spring Data `@Query("SELECT u FROM User u WHERE ...")` (JPQL) produces a TypeORM `repo.createQueryBuilder('u').where(...)` call when straightforward, or a raw-SQL `dataSource.query(...)` with a TODO comment when the JPQL is too complex for QueryBuilder (verified by two fixture tests).
5. Rendering a fixture whose class imports `org.springframework.hateoas.EntityModel` produces output with the wrapper stripped AND a TODO comment containing the original `EntityModel.of(...)` link configuration text from the source (verified by a fixture test asserting both the stripped return type and the presence of the TODO).
6. Rendering a fixture whose class is annotated with `@PreAuthorize("hasRole('ADMIN')")` under the default policy produces `SelectionResult.refused["UserAdminController"] == "security"` and the class does NOT appear in the output dict (verified by an integration test).
7. Rendering the same fixture with `--permissive-features` produces an output file containing a TODO comment naming `@PreAuthorize` and a commented-out `@UseGuards(/* RolesGuard with role 'ADMIN' */)` line; the start-of-run log includes the loud "Permissive mode — output is NOT production-ready" warning (verified by integration test asserting log capture).
8. Rendering a fixture whose class imports `reactor.core.publisher.Mono` under the default policy produces `SelectionResult.refused["..."] == "webflux"` and the class does NOT appear in the output dict (verified by integration test).
9. Rendering a fixture with `@ConfigurationProperties(prefix="datasource")` produces a `src/config/datasource.config.ts` file with `class-validator` decorators AND a `src/config/datasource-config.module.ts` file with a `useFactory` provider that calls `validateSync` (verified by fixture test).
10. Rendering a fixture with a Lombok `@Data` class produces a plain TypeScript class with public fields and a JSDoc trailer noting the original `@Data` annotation (verified by fixture test); rendering a `@Value` class produces `public readonly` fields and an all-args constructor (verified by separate fixture test).
11. Rendering a fixture with a controller that has `@Body() @Valid CreateUserDto dto` produces `@Body() dto: CreateUserDto` AND the `CreateUserDto` class with the appropriate `@IsEmail()`, `@MinLength()`, `@IsOptional()`, etc. decorators from the source's JSR-380 annotations (verified by fixture test).
12. Rendering with `db_layer=raw_only` produces zero `@Entity`-decorated classes; every repository uses `private readonly ds: DataSource` and `await this.ds.query(...)` (verified by integration test).

## Pros and Cons of the Considered Options

### Fork 1 — DI translation

**(a) faithful 1:1 with module wiring and stereotype JSDoc. ✅ Chosen.**
* Good, because NestJS DI and modern Spring DI are conceptually identical; the 1:1 mapping reads as idiomatic in both.
* Good, because per-feature module files close the legacy gap of users hand-writing `<domain>.module.ts`.
* Good, because stereotype JSDoc costs ~2 lines per class and pays back at review time when comparing source vs output.
* Good, because `@Qualifier` handling is a local transformation, not a new abstraction.
* Bad, because all stereotypes (`@Service`, `@Repository`, `@Component`) collapse to `@Injectable()` — loses some semantic signal (mitigated by JSDoc).
* Bad, because the renderer must know which domain a controller/service belongs to (already known via ADR-009's domain grouping).

**(b) minimal decorators.**
* Good, because less decorator noise.
* Bad, because it fights the framework — NestJS docs and ecosystem use `@Injectable()`.
* Bad, because module files become verbose (explicit `{ provide, useClass }` for every provider).
* Bad, because output looks like a junior dev who did not read the NestJS docs.

**(c) property-based DI mirroring Spring field injection.**
* Good, because it is a closer textual mirror to Java field-injection style.
* Bad, because it is an anti-pattern in NestJS; the community moved to constructor DI.
* Bad, because it is harder to test (cannot pass mocks via constructor).
* Bad, because Spring itself moved away from field injection in 4.3+; translating to it is a regression.

**(d) hybrid by complexity.**
* Good, because it could match each case optimally in theory.
* Bad, because the renderer needs heuristics to decide "simple vs complex" — adds branching.
* Bad, because inconsistent output (some services use shorthand, others do not) is harder to review.

### Fork 2 — HTTP layer

**(a) strict 1:1 faithful (edge cases unhandled).**
* Good, because the mental model is trivial.
* Bad, because `ResponseEntity`, `HttpServletRequest`, and content negotiation get hallucinated; outputs may not compile or behave wrong.
* Bad, because it perpetuates the same legacy failure mode.

**(b) strict 1:1 + explicit edge-case rule table. ✅ Chosen.**
* Good, because it preserves the per-class output shape and the side-by-side reviewability of source against output.
* Good, because edge cases are handled deliberately, not hallucinated.
* Good, because the rules are deterministic — same input produces the same output structure.
* Good, because TODO comments preserve the human review surface for cases the rules cannot fully handle.
* Bad, because the prompt becomes longer (table of edge-case rules), increasing prompt-token budget per render call.

**(c) per-endpoint controller.**
* Good, because SRP per controller.
* Bad, because a 28-method controller becomes 28 files — file explosion.
* Bad, because it is not idiomatic NestJS; the community uses grouped controllers.
* Bad, because it loses the semantic grouping that was in the Spring source.

**(d) hybrid split by sub-resource.**
* Good, because individual file size stays manageable.
* Bad, because the renderer needs split heuristics — inconsistent across runs (determinism risk).
* Bad, because it loses the "1 source file → 1 output file" property Fork 8 will lock.
* Bad, because reviewers cannot easily trace `findUserOrders` to its new home.

### Fork 3 — HATEOAS

**(a) drop entirely.**
* Good, because zero complexity in the renderer or prompt.
* Good, because output is clean idiomatic NestJS.
* Bad, because silent semantic loss — reviewer reading the output has no idea source had `_links` that disappeared.
* Bad, because projects depending on HATEOAS clients break.

**(b) legacy three-mode configurable (`self`/`full`/`none`).**
* Good, because it is familiar to legacy users.
* Bad, because `full` was always a stub; users hit a runtime error or partial implementation.
* Bad, because default `self` pollutes output for projects that do not use HATEOAS.
* Bad, because it does not detect source usage — runs blind.

**(c) auto-detect + wrapper strip + TODO with original link text. ✅ Chosen.**
* Good, because it preserves clean output for the 90%+ of projects without HATEOAS.
* Good, because it is honest about what was lost when HATEOAS is present.
* Good, because wrapper stripping logic is the same edge-case handling Fork 2 already added for `ResponseEntity`.
* Good, because no config knob; behavior follows source.
* Bad, because the `Page<T>` interface in the scaffold is one extra template file (small one-time cost).

**(d) auto-detect + emit minimal self-link helper.**
* Good, because the `self` link survives.
* Bad, because it adds a utility file even when only half-used.
* Bad, because richer links (related-resources, actions) are still lost — partial fidelity, still TODO required.
* Bad, because mandatory request injection (`@Req() req: Request`) fights Fork 2's preference for typed params.

### Fork 4 — Persistence

**(a) TypeORM two-tier + callback `@Transactional` + configurable `db_layer`. ✅ Chosen.**
* Good, because JPA `@Entity` → TypeORM `@Entity` is the cleanest cross-ecosystem decorator translation in the entire ADR.
* Good, because the two-tier approach honestly addresses the QueryDSL / Blaze reality without producing silently wrong queries.
* Good, because per-class rendering (Fork 8) fits naturally — one entity is one file.
* Good, because configurability via `db_layer` accommodates users who want one pattern throughout (`typeorm_only`) or no ORM at all (`raw_only`) without abandoning the recommended default.
* Bad, because two tiers means two patterns to review (TypeORM ergonomics plus raw SQL strings).
* Bad, because raw SQL loses TypeORM's compile-time query validation — must be reviewed for SQL injection (parameterized only; never interpolated).

**(b) TypeORM all-in.**
* Good, because one pattern throughout.
* Bad, because TypeORM QueryBuilder cannot faithfully express Blaze Persistence entity views, window functions, or complex projections — output will be subtly incorrect.
* Bad, because the LLM produces plausible-looking but wrong QueryBuilder code — the exact failure mode the chosen option avoids.

**(c) Prisma.**
* Good, because best type safety in the TS ecosystem.
* Bad, because architecturally incompatible with per-class rendering — Prisma needs the whole entity set known at once.
* Bad, because custom queries still need raw SQL — no improvement on the complex-query tier.
* Bad, because JPA decorator semantics do not survive translation.

**(d) typed interfaces + raw SQL only (no ORM).**
* Good, because maximum flexibility.
* Good, because predictable output (no ORM magic).
* Bad, because the `@Entity` → entity-class mapping fidelity is lost; every relationship is manual joins.
* Bad, because trivial CRUD becomes verbose hand-rolled SQL.

**(e) configurable with all four modes.**
* Good, because maximum flexibility at the contract level.
* Bad, because the renderer must implement and test every mode — 4× test surface, 4× prompt rules.
* Bad, because it punts the design call; defaults still pick a winner.

### Fork 5 — Exception translation

**(a) `HttpException` subclasses + generated `ExceptionFilter`. ✅ Chosen.**
* Good, because Spring's exception model and NestJS's are conceptually identical — same throw + framework-aware base classes + centralized handlers.
* Good, because adding `@ControllerAdvice` translation closes a real legacy gap.
* Good, because the per-exception mapping table is short and citeable.
* Good, because response shape is preserved by default — NestJS `HttpException` produces responses close to Spring Boot defaults.
* Bad, because services become HTTP-aware (throw HTTP-tagged exceptions) — a Spring pattern some teams strictly avoid.

**(b) plain `Error` subclasses + central filter translates.**
* Good, because services are HTTP-agnostic — cleaner architecture.
* Good, because services are easier to reuse in non-HTTP contexts.
* Bad, because it diverges structurally from legacy and source — output has a different exception hierarchy.
* Bad, because the renderer must maintain a `ERROR_TO_STATUS` mapping table per project — more scaffold complexity.

**(c) `Result<T, E>` functional pattern.**
* Good, because explicit error paths in the type signature.
* Good, because no hidden control flow.
* Bad, because every method signature changes — massive structural rewrite.
* Bad, because it is alien to NestJS norms.
* Bad, because translation fidelity is gone — Spring threw exceptions; TS uses `Result`.

**(d) hybrid (services throw plain `Error`; controllers `try/catch` and rethrow).**
* Good, because clean layering between domain and HTTP layers.
* Bad, because verbose `try/catch` in every controller method.
* Bad, because it defeats NestJS's exception-filter pattern (the whole point is to avoid controller try/catch).

### Fork 6 — Configuration and properties

**(a) minimal string lookups.**
* Good, because low complexity, small scaffold footprint.
* Good, because `.env` is universal and CI-friendly.
* Bad, because no type safety on config values — every lookup is `string` or string-coerced.
* Bad, because `@ConfigurationProperties` typed-binding semantics are lost — major fidelity loss.

**(b) full typed everywhere.**
* Good, because honors `@ConfigurationProperties` semantics fully.
* Good, because idiomatic modern NestJS.
* Bad, because forces typed classes even for one-off `@Value` properties that have no natural grouping.
* Bad, because over-engineering for stragglers.

**(c) YAML mirror.**
* Good, because user's existing `application.yml` mostly works.
* Good, because `@Profile` translation is natural (file-per-profile).
* Bad, because it diverges from NestJS norm (NestJS strongly prefers `.env`).
* Bad, because production deployment is messier — most cloud platforms inject env vars natively, not YAML files.

**(d) hybrid (typed for `@ConfigurationProperties`; typed inline for `@Value`). ✅ Chosen.**
* Good, because it preserves the typed-binding architectural mirror for grouped configs.
* Good, because pragmatic handling for stragglers (typed inline `configService.get(..., { infer: true })` plus a TODO nudging the user to group later).
* Good, because cloud-deployment-friendly (`.env` everywhere).
* Good, because no new dependency burden in v1 (`class-validator` is already required for Fork 7).
* Bad, because medium scaffold complexity (one config class plus one provider module per `@ConfigurationProperties`).

### Fork 7 — DTO and Bean Validation

**(a) class-based DTOs + global `ValidationPipe`. ✅ Chosen.**
* Good, because Spring `@Valid` + JSR-380 and NestJS `class-validator` + `ValidationPipe` are the cleanest cross-ecosystem analogue in the whole ADR.
* Good, because global pipe registration prevents the most likely bug — per-endpoint pipes risk a new endpoint silently accepting unvalidated input.
* Good, because no new dependencies (`class-validator` + `class-transformer` already needed for Fork 6).
* Good, because `@Valid` cascade has a direct analogue (`@ValidateNested() + @Type`).
* Bad, because constructor-param decorators on records require `class-transformer` configuration knowledge.

**(b) interface-only DTOs.**
* Good, because lightest scaffolding.
* Bad, because no runtime validation possible — `ValidationPipe` requires class-based DTOs.
* Bad, because it silently drops every JSR-380 annotation from source.
* Bad, because output accepts malformed input — a security regression.

**(c) zod schemas.**
* Good, because modern, type-inferred, popular.
* Good, because lighter runtime than `class-validator`.
* Bad, because it diverges structurally from Spring source — schema-object vs decorator-on-field.
* Bad, because it requires a custom `ZodValidationPipe` in scaffold.
* Bad, because `class-transformer` is already needed for Fork 6 — adding zod doubles validation vouch surface.

**(d) class-based + per-endpoint `@UsePipes`.**
* Good, because explicit per endpoint.
* Bad, because massive boilerplate duplication.
* Bad, because easy to forget on a new endpoint → silent acceptance.

### Fork 8 — Render granularity

**(a) per-class + Lombok intent-mapping. ✅ Chosen.**
* Good, because cache reuse is the dominant economic factor — change one class, invalidate one cache entry.
* Good, because parallelism is cleanest at per-class (renderer concurrency 5 gives near-linear speedup).
* Good, because failure isolation matters under non-zero LLM failure rates.
* Good, because per-class avoids the chunk_max_chars cliff entirely.
* Good, because Lombok intent-mapping matches Fork 7's existing rules.
* Bad, because no cross-class coherence within a single call — relies on graph data being in the prompt.

**(b) per-file.**
* Good, because same as (a) in the common case of one class per file.
* Bad, because giant outer + many small inner classes produce large prompts.
* Bad, because changing one inner class re-renders the entire file.

**(c) per-domain.**
* Good, because cross-class coherence — all related classes visible in one prompt.
* Good, because fewer LLM calls overall.
* Bad, because cache reuse plummets — one class change invalidates the whole domain.
* Bad, because prompt size scales with cap; chunk_max_chars budget gets uncomfortable.
* Bad, because failure isolation is poor — one structured-response failure invalidates all N files.

**(d) per-class default with interface field for future per-domain.**
* Good, because same operational properties as (a).
* Neutral, because the chosen option already includes the `render_strategy` forward-pointer field as the migration path.

### Fork 9 — Coverage matrix and encounter behavior

**(X) TODO + skip.**
* Good, because output still compiles and runs.
* Good, because TODO is reviewable.
* Bad, because silently insecure — endpoint rendered without auth check; reviewer might miss the TODO.
* Bad, because it loses the most important signal (the security constraint).

**(Y) stub + TODO.**
* Good, because reviewable AND nudges the user toward the correct fix.
* Good, because commented-out import plus decorator means a one-line uncomment to apply.
* Bad, because more verbose output than (X).

**(Z) refuse to render.**
* Good, because impossible to miss; safest for security-sensitive cases.
* Bad, because it disrupts the preview UX — a security-heavy project might render nothing.
* Bad, because per-class refuse noise on the runner's terminal.

**(W) hybrid (stub + TODO default; refuse for Security; refuse WebFlux) + configurable + CLI presets. ✅ Chosen.**
* Good, because security failures are loud — `@PreAuthorize` silently dropped becomes impossible without explicit opt-in.
* Good, because everything else stays reviewable as stub + TODO — a one-line uncomment fix.
* Good, because configurability accommodates the disruption-vs-security tradeoff per user.
* Good, because the coverage matrix becomes the source of truth for the project's honest disclosure list.
* Bad, because three policy fields plus two CLI presets adds API surface; users must understand the default-recommended-policy semantics.

## More Information

### Relationships

* **ADR-001** (project skeleton) — `TypeScriptConfig` flows through `Settings.renderers.typescript` via the standard pydantic-settings priority chain; CLI presets `--strict-features` / `--permissive-features` resolve to coherent combinations of the policy fields.
* **ADR-003** (parsing strategy) — the per-decorator mapping tables in Forks 2, 4, 5, 6, 7, 8 depend on the Spring annotation taxonomy in ADR-003's amendment. Comprehensive annotation coverage is a prerequisite for correct translation.
* **ADR-004** (complexity model) — does not directly drive translation but provides the bucketing metrics ADR-009 uses to select which classes get translated.
* **ADR-005** (token utilization) — per-class render granularity (Fork 8) keeps each prompt safely under `chunk_max_chars` regardless of domain size.
* **ADR-006** (knowledge graph schema) — the renderer consumes graph nodes and edges (including `unresolved_call` edges) plus LLM annotations as the input to per-class translation.
* **ADR-008** (pluggable renderer interface) — the `Renderer[TypeScriptConfig]` generic binding, the `RendererRegistry.register("typescript")` decorator, and the scaffold-templates strategy are all populated by this ADR.
* **ADR-009** (rendering budget cap) — `ClassSelector` produces the filtered subgraph this renderer receives; `SelectionResult` is extended with `refused`, `stub_todos`, and `feature_policies_active` fields so encounter-behavior audit surfaces alongside selection audit.
* **ADR-013** (LLM provider abstraction) — render calls flow through the standard middleware stack (Telemetry → Caching → Retry → Provider); `Purpose.RENDER` + `Tier.RENDER` enums already shipped.
* **ADR-014** (prompt versioning) — the render prompt lives at `codeograph/renderers/typescript_nestjs/prompts/render_file/v1.md`; Jinja2 `StrictUndefined` engine is reused for both the prompt and the scaffold templates.
* **ADR-015** (telemetry + response cache) — per-class granularity (Fork 8) maximizes cache reuse; `rendered_input_hash` is part of the cache key.

### Deferred items

* **Service-layer error layer (`service_error_layer = http_aware | domain_only`)** — Fork 5 retrofit deferred. Add `domain_only` mode in v1.1 only if a real user requests HTTP-agnostic services. Requires two new scaffold files (`DomainError` base, `DomainErrorFilter`), a parallel translation table, and a per-project error-to-status registry.
* **`render_strategy = per_domain` mode** — Fork 8 forward-pointer. Adds cross-class coherence at the cost of cache reuse; trigger condition is a real correctness problem the per-class prompt cannot solve via graph-data injection.
* **Spring HATEOAS full `_links` translation** — Fork 3 v1.1 row. Requires picking a TypeScript HATEOAS library (or hand-rolling assemblers).
* **Lombok `@Builder` (basic shape) and `@With`** — Fork 7/8 v1.1 row.
* **Custom `ConstraintValidator` logic porting** — Fork 7 v1.1; v1 produces only a TS skeleton.
* **WebFlux best-effort translation (`webflux_policy = best_effort`)** — available as opt-in in v1 but output requires manual review; v1.1 may stabilize.
* **All Async / Scheduling / Events / Caching / Security / AOP / Filters-Interceptors / File-upload / Lifecycle / i18n / Boot-Actuator / Tests categories** — every row in the coverage matrix's v1.1 column.
* **Spring Cloud / Batch / Integration / Messaging / Native / DevTools / custom Boot starters / custom `BeanPostProcessor`** — every row in the matrix's out-of-scope column; explicit refuse-to-render or no-op.

### Open Questions / Future Work

* Did the per-decorator mapping tables (Forks 2, 4, 5, 6, 7) hold up against real-world Spring projects, or did edge cases emerge?
* Did `db_layer = typeorm_2tier` produce correct output for projects with mixed QueryDSL and standard CRUD?
* Did `security_feature_policy = refuse` default produce too many refused classes on security-heavy projects, or was the user-friction acceptable?
* Did `webflux_policy = refuse` ever surface in eval corpora (i.e., are there real reactive Spring projects evaluators want to preview)?
* Did Lombok intent-mapping handle the supported annotations correctly, or did `@Builder` translation produce wrong code?
* Did per-class granularity hit the `chunk_max_chars` budget on any class, or did class-sized prompts stay safely under?
* Did the generated `<domain>.module.ts` files compile and wire correctly on the first run, or did manual fixups become a pattern?
* Did `stub_todo` TODOs surface in scorecards at a rate that suggests too much was deferred, or did the coverage matrix reflect real v1 priorities?

### References

* NestJS Documentation — Controllers, Providers, Modules, Pipes, Exception Filters, Configuration. https://docs.nestjs.com/
* TypeORM Documentation — Entities, Repositories, DataSource, Transactions. https://typeorm.io/
* `class-validator` — https://github.com/typestack/class-validator
* `class-transformer` — https://github.com/typestack/class-transformer
* Spring Framework Reference — Annotation taxonomy used as the source side of the mapping.
* MADR template — https://github.com/adr/madr

---

## Amendments

### 2026-05-28 — Remove `unsupported_feature_policy="refuse"` (DC3 Fixup Round 01, Issue #6 Path B)

**Change:** `UnsupportedFeaturePolicy` narrowed from `Literal["stub_todo", "silent_skip", "refuse"]` to `Literal["stub_todo", "silent_skip"]`. Passing `refuse` to `TypeScriptConfig` now raises a Pydantic `ValidationError`.

**Rationale:** The original `refuse` value was a policy without a detection signal. `security_feature_policy="refuse"` and `webflux_policy="refuse"` both work because they have concrete, deterministic class-level signals — Spring Security annotations (`@PreAuthorize`, `@Secured`, etc.) and reactive return types (`Mono<T>`, `Flux<T>`) respectively. Generic "unsupported Spring features" have no equivalent class-level detector. Implementing one would require a feature-by-feature annotation scan, and `stub_todo` already surfaces the gap reviewably in the generated output. Keeping `refuse` as a valid value was a dead code path that misled callers.

**Files changed:** `config.py` (Literal narrowed + docstring), `prompts/render_file/v1.md` (refuse bullet removed), `tests/renderers/test_typescript_config.py` (test now validates that `"refuse"` raises).

**2026-06-21 — DC3 design-review pass (1 decision + 1 shared boundary + 1 cross-ref).** A code-blind design review of ADR-010 (DC3 cluster, guideline 06) produced one locked decision plus a shared boundary; the Spring→TS mapping decisions themselves (learner-zone) were not touched.

1. **Refuse-reason precedence for multi-category classes (D-010-2).** When a class is both security-refused and webflux-refused, the audit log records **security first (most-severe-first)**. The outcome is identical (the class is refused either way) — this only fixes reason-attribution determinism. Fork 9's sub-rules are amended: precedence = security > webflux.

**Shared boundary (D-010-1, cross-ADR 008/009/010).** Selection-tuning knobs (per-domain cap, domain grouping/mapping) are hosted on the renderer config (`TypeScriptConfig`) for v1, documented as **ADR-009 selection knobs hosted on the renderer config — not renderer concerns**; revisit (→ dedicated selection-config object) at the 2nd renderer (v1.1).

**Cross-reference (D-008-1).** ADR-010 finding #2 (renderer input contract — typed vs opaque `annotations`) is resolved in **ADR-008's amendment of the same date**: `annotations` is an opaque `dict[str, object]` with an in-memory handoff.

**New Confirmation item (from this amendment):**
* A class matching both security and webflux refusal records `security` as the refuse reason in the audit log (D-010-2).

No reversal of any prior decision; clarification only.
