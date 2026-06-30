# ormguard — 사용 가이드

## 설치 (개발/POC)

```bash
cd ormguard
pip install -e ".[dev]"
```

## 0. 설치 없이 동작 확인 (self-check)

운영 프로젝트나 외부 DB 없이, 일부러 drift를 심은 인메모리 SQLite로 즉시 시연:

```bash
python -m ormguard --selfcheck
```

출력 예:

```
# selfcheck (in-memory sqlite)
  [ERROR] column_missing @ users.nickname — entity maps this column but the database has no such column
  [ERROR] table_missing @ orders — ORM declares this table but it is absent from the database
  [WARN] nullable_mismatch @ users.age — entity nullable=False but database nullable=True
  [WARN] column_extra @ users.legacy_points — database column not mapped by any entity (silently unused)
  -> 2 error(s), 2 warning(s)
```

## 1. 함수로 검증 (프레임워크 무관)

```python
from ormguard import validate, assert_schema

report = validate(engine, Base)          # 절대 raise 안 함 — 결과를 들여다봄
if not report.ok:
    print(report.format_text())

assert_schema(engine, Base, strict=True) # ERROR면 SchemaValidationError
```

## 2. FastAPI 부팅 가드

```python
from ormguard.integrations.fastapi import schema_guard_lifespan

app = FastAPI(lifespan=schema_guard_lifespan(engine, Base, strict=True))
# strict=True -> ERROR drift면 앱이 부팅을 거부 (= Hibernate validate)
# strict=False -> 경고만 로그하고 서비스는 뜸
```

## 3. CI (exit code)

```bash
python -m ormguard --url "$DATABASE_URL" --metadata myapp.db:Base --schema aivelabs_sv
# ERROR finding이 있으면 exit 1
```

옵션: `--check-types`(타입 비교 켜기), `--no-nullable`, `--no-extra`,
`--ignore-table NAME`(반복 가능), `--warn-only`(에러여도 exit 0).

## 4. 멀티테넌트 (ORM 하나, DB 여러 개)

```python
from ormguard import validate_many, format_matrix

reports = validate_many({"larosee": e1, "hmall": e2, "cafe24": e3}, Base)
print(format_matrix(reports))
# larosee   2E/1W
# hmall     OK
# cafe24    OK
```

## 5. 설정 (Config)

```python
from ormguard import Config, Severity, validate
from ormguard.model import NULLABLE_MISMATCH

cfg = Config(
    schemas={"aivelabs_sv"},                 # 이 스키마만 검사
    ignore_tables={"alembic_version"},
    ignore_columns={"users.legacy_flag"},
    check_types=True,                        # 타입 비교 켜기
    severity_overrides={NULLABLE_MISMATCH: Severity.ERROR},  # nullable도 치명적으로
)
validate(engine, Base, cfg)
```

## 자체 테스트 실행

```bash
pytest        # 인메모리 SQLite, 외부 DB 불필요
```
