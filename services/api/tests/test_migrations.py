"""Migration reversibility and model/migration parity tests."""

from conftest import alembic_config, database_url
from sqlalchemy import create_engine, inspect

from alembic import command
from app import rules_models
from app.models import Base

EXPECTED_TABLES = {
    "alembic_version",
    "audit_events",
    "auth_sessions",
    "business_profiles",
    "calculation_versions",
    "calculations",
    "organization_memberships",
    "organizations",
    "rule_definitions",
    "rule_sources",
    "rule_versions",
    "tax_profiles",
    "users",
}


def test_migration_upgrade_downgrade_upgrade_is_reversible() -> None:
    """The complete schema must survive a full migration round trip."""

    url = database_url()
    config = alembic_config(url)

    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
    finally:
        engine.dispose()

    command.downgrade(config, "base")
    engine = create_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    command.check(config)


def test_migrated_columns_match_declared_metadata(db_engine) -> None:
    """Manual migrations and SQLAlchemy metadata must not silently drift."""

    assert rules_models.RuleSource.__tablename__ in Base.metadata.tables
    inspector = inspect(db_engine)
    for table_name, table in Base.metadata.tables.items():
        migrated_columns = {column["name"] for column in inspector.get_columns(table_name)}
        assert migrated_columns == set(table.columns.keys())
