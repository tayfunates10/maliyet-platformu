"""Migration reversibility, revision safety and model/migration parity tests."""

from alembic.script import ScriptDirectory
from conftest import alembic_config, database_url
from sqlalchemy import create_engine, inspect

from alembic import command
from app import (
    auth_context,
    decision_analysis_models,
    partner_api_models,
    password_auth,
    rules_models,
    widget_branding_models,
)
from app.models import Base

ALEMBIC_VERSION_NUM_MAX_LENGTH = 32


def expected_tables() -> set[str]:
    """Derive the schema contract from registered SQLAlchemy metadata.

    The Alembic bookkeeping table is the only table not declared on ``Base``.
    Importing model modules above ensures all application tables are registered.
    """

    assert auth_context.AuthSession.__tablename__ in Base.metadata.tables
    assert password_auth.UserCredential.__tablename__ in Base.metadata.tables
    assert rules_models.RuleSource.__tablename__ in Base.metadata.tables
    assert decision_analysis_models.DecisionAnalysisArtifact.__tablename__ in Base.metadata.tables
    assert partner_api_models.PartnerApiCredential.__tablename__ in Base.metadata.tables
    assert widget_branding_models.WidgetBrandingProfile.__tablename__ in Base.metadata.tables
    assert widget_branding_models.WidgetPresentationSnapshot.__tablename__ in Base.metadata.tables
    assert widget_branding_models.WidgetPublishedPresentation.__tablename__ in Base.metadata.tables
    return {"alembic_version", *Base.metadata.tables.keys()}


def test_alembic_revision_contract_is_safe_for_default_version_table() -> None:
    """Reject revision IDs that would overflow Alembic's default VARCHAR(32)."""

    config = alembic_config("postgresql+psycopg://contract:contract@127.0.0.1/contract")
    script = ScriptDirectory.from_config(config)
    revisions = list(script.walk_revisions())

    assert revisions
    assert len(script.get_heads()) == 1, "migration history must have exactly one head"

    revision_ids = [item.revision for item in revisions]
    assert len(revision_ids) == len(set(revision_ids)), "migration revision IDs must be unique"

    too_long = [
        revision_id
        for revision_id in revision_ids
        if len(revision_id) > ALEMBIC_VERSION_NUM_MAX_LENGTH
    ]
    assert not too_long, (
        "Alembic revision IDs exceed the default version_num VARCHAR(32): " + ", ".join(too_long)
    )


def test_migration_upgrade_downgrade_upgrade_is_reversible() -> None:
    """The complete schema must survive a full migration round trip."""

    url = database_url()
    config = alembic_config(url)

    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) == expected_tables()
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

    inspector = inspect(db_engine)
    for table_name, table in Base.metadata.tables.items():
        migrated_columns = {column["name"] for column in inspector.get_columns(table_name)}
        assert migrated_columns == set(table.columns.keys())
