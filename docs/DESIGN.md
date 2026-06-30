# ormguard — 설계 문서

## 1. 풀려는 문제

SQLAlchemy ORM에서는 **Entity(ORM 모델)와 실제 DB 스키마가 어긋나 있어도 서버가
정상적으로 뜬다.** 부팅 시점에 둘을 대조하는 단계가 없기 때문이다.

- Entity엔 컬럼이 있는데 DB엔 없음 → 그 컬럼을 건드리는 요청이 들어오는 순간
  런타임에 `column does not exist`로 터진다.
- DB엔 컬럼이 있는데 Entity엔 없음 → 조용히 안 쓰인다. (마이그레이션은 됐는데
  매핑을 안 한 경우 등)

운영 중에 특정 기능을 실행해야만 발현되므로, 배포 직후가 아니라 한참 뒤에
프로덕션에서 발견되는 경우가 많다.

## 2. JPA/Hibernate와의 대비 (핵심 착안점)

JPA/Hibernate에는 `hibernate.ddl-auto=validate`가 있다. 앱이 부팅될 때
모든 Entity를 살아있는 DB 스키마와 대조하고, 하나라도 안 맞으면
`SchemaManagementException`을 던지며 **앱이 아예 뜨지 않는다.** 덕분에
"Entity≠DB인데 서비스가 멀쩡히 돌다가 나중에 터지는" 일이 구조적으로 막힌다.

SQLAlchemy에는 이 validate가 없다. `create_all()`은 없는 테이블만 만들 뿐
기존 스키마를 검증하거나 변경하지 않는다.

> **ormguard = Hibernate `ddl-auto=validate`의 SQLAlchemy 판.**

## 3. 두 가지 다른 "정합 검사"를 구분한다

같은 목표(Entity↔DB 정합)지만 **검사 시점**이 다른 두 접근이 있다. ormguard의
코어는 **A**이고, B는 멀티테넌트용 advanced 모드로 로드맵에 둔다.

| | **A. 런타임 validate (코어)** | **B. 오프라인 마이그레이션 replay (로드맵)** |
|---|---|---|
| 무엇과 비교 | Entity ↔ **실제 연결된 DB** | Entity ↔ **마이그레이션이 만들 스키마** |
| DB 필요? | 필요 (런타임에 붙는 그 DB) | 불필요 (정적) |
| 언제 | 앱 부팅 시 / CI에서 DB 대상 | CI에서, DB 만들기 전 |
| 잡는 것 | **모든** drift (수동 DB 수정, ETL이 바꾼 것, 마이그레이션 누락 전부) | 마이그레이션 분기 버그, "신규 테넌트가 깨질 것" |

- **A**는 실제 DB를 보므로 원인 불문 다 잡지만, 그 DB에 붙어야 알 수 있다.
- **B**는 DB 없이 미래 테넌트까지 예측하지만, 마이그레이션 경로로 들어온 drift만 본다.

## 4. 기존 도구로 안 되는 이유

- **`alembic check`**: 살아있는 DB 하나를 가리켜 autogenerate로 비교한다.
  CI/개발 도구이고, autogenerate에는 알려진 사각지대가 있다(server_default 기본
  off, 한쪽이 default값이면 타입 비교 skip 등). 무엇보다 "앱이 지금 붙는 그 DB가
  맞는지"를 부팅 시점에 보장하지 않는다.
- **Atlas**: 살아있는 DB + drift detection이 유료. Go 바이너리라 파이썬 스택에
  무겁게 얹힌다.
- **migra / sqlalchemy-diff**: DB↔DB diff. Entity↔살아있는 DB 비교가 아니다.

ormguard는 "앱이 막 사용하려는 그 DB를, 부팅하는 순간" 검증한다는 점이 다르다.

## 5. v1 검사 항목

| Finding | 기본 심각도 | 의미 |
|---|---|---|
| `table_missing` | ERROR | Entity가 선언한 테이블이 DB에 없음 |
| `column_missing` | ERROR | Entity 컬럼이 DB에 없음 (런타임 크래시 케이스) |
| `column_extra` | WARN | DB 컬럼이 어떤 Entity에도 매핑 안 됨 |
| `nullable_mismatch` | WARN | NOT NULL / NULL 불일치 |
| `type_mismatch` | WARN (opt-in) | 컬럼 타입 불일치 — 기본 off (dialect 의존) |

설계 원칙: **false positive를 낮춘다.** 존재 여부(런타임에 실제로 터지는 것)는
ERROR, 구조적 뉘앙스는 WARN, 타입 비교는 켤 때만. PK 컬럼은 항상 NOT NULL이라
일부 dialect(SQLite)가 nullable로 잘못 리플렉션해도 nullable 비교에서 제외한다.

DB 전체를 스캔하지 않고 **ORM이 아는 테이블만** 리플렉션한다. 그래서
`alembic_version`이나 ETL 소유 테이블 같은 무관한 것이 노이즈로 잡히지 않는다.
"DB에 있는데 Entity엔 없는 컬럼"은 매핑된 테이블 **안에서만** 본다.

v1 제외(→ v2): index, FK, default, check constraint, enum.

## 6. 아키텍처

```
validate(engine, Base, config)
  ├─ orm.build_expected(metadata)      # ORM 목표 스키마  → {(schema,table): TableInfo}
  ├─ reflect.reflect_actual(engine)    # 실DB 스키마(Inspector) → 같은 형태
  └─ diff.diff_schemas(expected, actual) → [Finding]  → ValidationReport
```

- `_schema.py` — 양쪽이 공유하는 정규화 표현(ColumnInfo / TableInfo).
- `model.py` — Severity, Finding, ValidationReport, SchemaValidationError.
- `config.py` — schema 제한, ignore, severity override, 토글.
- `integrations/fastapi.py` — `schema_guard_lifespan(...)` 부팅 가드.
- `cli.py` — `python -m ormguard` (CI exit code) + `--selfcheck`.
- `core.py` — `validate`, `assert_schema`, `validate_many`, `format_matrix`.

순수 SQLAlchemy 의존. FastAPI는 optional.

## 7. 검증 전략

- **자체 검증**: `tests/test_core_sqlite.py` — 인메모리 SQLite에 일부러 drift를
  심고 4종 finding을 모두 잡는지 확인. 외부 DB·운영 프로젝트 불필요.
- **자체 데모**: `python -m ormguard --selfcheck` — 한 줄로 동작 시연.
- **실전 검증(예정)**: 실제 `aace-api` 한 테넌트 DB에 붙여, 수동 감사
  (`aace-api/docs/alembic_orm_drift_audit.md`)가 잡은 컬럼 누락
  (`campaign_sets.campaign_group_id` 등)을 ormguard도 잡는지 대조.

## 8. 로드맵

- **v1** (현재): 런타임 Entity↔DB validate, FastAPI 가드, CLI, 멀티테넌트 매트릭스.
- **v1.x**: index/FK/default 검사, 타입 정규화 개선, 더 많은 dialect 테스트, CI 액션.
- **v2 (차별점)**: 오프라인 멀티테넌트 Alembic replay. 테넌트 프로파일
  `[(platform_type, database_name), …]`을 입력받아 마이그레이션을 오프라인으로
  replay(op.* 후킹 + raw SQL DDL 파싱)하면서 분기를 실제 실행 → 테넌트별 산출
  스키마를 만들고 ORM과 diff. **DB 없이 "신규 테넌트가 깨질 것"을 예측**한다.
  기존 어떤 도구도 안 하는 영역.

## 9. 동기가 된 실제 사례 (멀티테넌트)

`aace-api`는 PostgreSQL 멀티테넌시로, 마이그레이션 66개 중 40개가
`connection.engine.url.database`(=mall_id)와 `platform_type`으로 분기한다. 같은
마이그레이션 셋인데 테넌트(larosee/hmall/cafe24/imweb)마다 다른 스키마가 된다.
수동 감사로 `campaign_sets.campaign_group_id` 전무(전 플랫폼 런타임 에러),
`enterprise_databases` 네이밍 버그로 신규 larosee 테넌트가 ETL 테이블을 빈
스키마로 선점하는 위험 등을 발견했다. 이 수동 감사를 자동화하는 것이 v2의 목표다.
