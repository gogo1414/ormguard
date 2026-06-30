# ormguard v2 — 오프라인 멀티테넌트 Alembic Replay (설계 착수)

> 상태: **설계(spec)**. 구현 전. v1(런타임 validate)과 독립적으로 켤 수 있는 모드.

## 1. 무엇을, 왜

v1은 *살아있는 DB*에 붙어 검증한다. 하지만 멀티테넌트 환경의 진짜 위험은
**"신규 테넌트를 마이그레이션으로 처음부터 만들면 어떤 스키마가 되는가"** 이고,
이건 그 테넌트 DB가 아직 존재하지 않으므로 v1으로는 볼 수 없다.

v2는 **DB 없이**, 마이그레이션을 테넌트 프로파일별로 오프라인 replay 해서 각
테넌트의 *산출 스키마*를 계산하고 ORM과 diff 한다. 즉 `aace-api`의 수동 감사
(`docs/alembic_orm_drift_audit.md`)를 자동화하는 것이 목표다.

`alembic check`/Atlas는 살아있는 DB 하나를 autogenerate로 비교할 뿐, 마이그레이션
내부의 `platform_type`/`database_name` **조건 분기를 실제 실행**해 테넌트별 결과를
시뮬레이션하지 못한다. 이 부분이 v2의 차별점이다.

## 2. 입력 / 출력

- **입력**
  - ORM 목표 스키마: `Base.metadata` (v1과 동일 추출기 재사용).
  - 마이그레이션 디렉터리: `migration/versions/**` (revision DAG).
  - 테넌트 프로파일 목록: `[(platform_type, database_name), …]`
    (예: `("larosee", "larosee_co_kr")`, `("cafe24", "cafe24shop")`).
    수동 지정 또는 `clients` 테이블 스냅샷(JSON)에서 로드.
- **출력**
  - 테넌트별 `ValidationReport` (v1과 동일 모델 재사용).
  - 테넌트 × finding 매트릭스 + 테넌트 간 divergence 리포트.

## 3. 핵심 메커니즘 — 오프라인 replay

문제: 마이그레이션은 `op.add_column(...)`, `op.create_table(...)`,
`op.execute("ALTER TABLE … / DO $$ … $$")` 같은 부수효과로 **실제 DB를 바꾸도록**
작성돼 있고, 분기는 `connection.engine.url.database`와
`context.get_x_argument()["platform_type"]`을 읽는다. DB 없이 결과 스키마를 알려면:

1. **인메모리 카탈로그**: `{(schema, table): TableInfo}` 를 들고, replay가 이걸
   변형하게 한다. (v1의 `_schema.TableInfo` 재사용.)

2. **`op.*` 후킹**: `alembic.op`의 주요 연산을 가로채 카탈로그에 반영.
   - `create_table`, `drop_table`
   - `add_column`, `drop_column`, `alter_column`
   - `create_index`/`drop_index`, `create_foreign_key` … (v2.1)
   - `op.execute(sql)` → 아래 4번 SQL 파서로 위임.
   - `op.bulk_insert`/데이터 변경 → 스키마엔 영향 없으니 무시.

3. **가짜 offline 커넥션/컨텍스트**: 분기 입력을 프로파일 값으로 주입.
   - `op.get_bind()` 가 반환하는 객체의 `.engine.url.database` 가 프로파일의
     `database_name` 을 돌려주도록 한다.
   - `context.get_x_argument(as_dictionary=True)` 가
     `{"platform_type": <프로파일>}` 를 돌려주도록 패치.
   - 이렇게 하면 마이그레이션의 `if database_name in [...]: return`,
     `if platform_type != "cafe24": return` 같은 가드가 **실제로 동작**한다.

4. **raw SQL DDL 파서** (`op.execute` 처리): `sqlglot`(PostgreSQL dialect)로
   파싱해 카탈로그에 적용.
   - 지원 대상: `CREATE TABLE`, `ALTER TABLE … ADD/DROP/ALTER COLUMN`,
     `DROP TABLE`, `CREATE INDEX`.
   - `DO $$ … $$` 익명 블록: 내부의 `ALTER TABLE …`/`IF NOT EXISTS` 멱등 패턴을
     best-effort로 추출(정규식 + sqlglot). 파싱 실패 시 **해당 statement를
     `unparsed`로 기록**하고 리포트에 "검증 불가" 플래그를 남긴다(조용히 무시 금지).
   - 순수 데이터 DML(`INSERT/UPDATE/DELETE`)은 스키마 무영향 → skip.

5. **revision 순서 replay**: down_revision DAG를 위상정렬하여 root→head 순서로
   각 `upgrade()` 를 호출. 브랜치/머지(`branch_labels`, 다중 head)도 DAG로 처리.
   각 테넌트 프로파일마다 깨끗한 카탈로그에서 처음부터 다시 replay.

## 4. diff & 리포트

- 테넌트별 산출 카탈로그 vs `Base.metadata` → **v1의 `diff_schemas` 그대로 재사용.**
- 추가 finding 종류:
  - `tenant_divergence`: 같은 테이블/컬럼이 테넌트마다 다르게 산출됨.
  - `unparsed_migration_sql`: replay가 해석 못한 raw SQL (수동 확인 필요, INFO/WARN).
- 출력: 테넌트 × 컬럼 매트릭스(감사 문서의 표와 동일 포맷).

## 5. 공개 API (예정)

```python
from ormguard.replay import replay_tenant, validate_migrations

# 단일 테넌트 산출 스키마
catalog = replay_tenant(
    migrations_dir="migration/versions",
    platform_type="larosee",
    database_name="larosee_co_kr",
)

# 여러 테넌트 × ORM diff
reports = validate_migrations(
    metadata=Base.metadata,
    migrations_dir="migration/versions",
    tenants=[("larosee", "larosee_co_kr"), ("cafe24", "cafe24shop")],
)
```

CLI: `python -m ormguard replay --migrations migration/versions --metadata src...:Base --tenants tenants.json`

## 6. 알려진 난점

- **raw SQL 커버리지**: 분기의 상당수가 `op.execute` raw SQL이라, 파서 커버리지가
  곧 정확도. 해석 못 한 건 반드시 `unparsed`로 노출(거짓 안심 방지).
- **타입 정규화**: v1과 동일 이슈. 존재/nullable 우선, 타입은 opt-in.
- **마이그레이션이 import하는 앱 코드**: 일부 마이그레이션이 모델/유틸을 import하면
  그 의존성이 따라온다. replay는 가능한 한 `op`/`sa` 레벨에서만 동작하도록 격리.
- **프로파일 소스**: 운영 `clients` 테이블 스냅샷을 어떻게 안전하게 제공할지(테스트
  픽스처 JSON 권장, 운영 접속 불필요).

## 7. 마일스톤

- **M1**: 카탈로그 + `op.*`(create_table/add/drop/alter_column) 후킹 + DAG replay.
  raw SQL 없이도 동작하는 단순 마이그레이션 셋으로 검증.
- **M2**: 가짜 offline 커넥션/`get_x_argument` 주입 → 분기 동작. `aace-api`의
  `a149c4ae450c`(order 컬럼, platform 분기) 케이스 재현.
- **M3**: sqlglot 기반 raw SQL DDL 파서 + `DO $$` 처리. 감사 문서의 #1~#7을
  자동 재현(= eval 통과 기준).
- **M4**: 테넌트 매트릭스 리포트 + CLI + `unparsed` 플래깅.

## 8. eval (정답지)

`aace-api/docs/alembic_orm_drift_audit.md` 가 그대로 정답지다. v2가 성공하려면
DB 없이 replay만으로 다음을 재현해야 한다:
`campaign_sets.campaign_group_id`/`is_group_added` 전무, `send_reservation.is_purchase`
전무, larosee `audience_predefiend_variables.order` 누락(AC-1014 회귀),
`enterprise_databases` 네이밍 버그로 인한 테넌트별 들쭉날쭉.
v1 테스트 `tests/test_aace_drift_cases.py` 가 일부를 이미 인코딩해 두었다.
