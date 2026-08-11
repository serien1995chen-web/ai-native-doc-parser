"""Unit tests for database access layer and ORM models."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import create_mock_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.core.database import get_db, init_db
from app.models import Base

pytestmark = pytest.mark.unit

EXPECTED_TABLES = {
    "users",
    "api_keys",
    "files",
    "file_identifications",
    "parse_tasks",
    "parse_results",
    "collections",
    "collection_items",
    "system_config",
}


def test_all_nine_business_tables_registered() -> None:
    assert set(Base.metadata.tables) >= EXPECTED_TABLES


def test_primary_keys_are_uuid() -> None:
    for table_name in EXPECTED_TABLES - {"system_config"}:
        table = Base.metadata.tables[table_name]
        pk_columns = list(table.primary_key.columns)
        assert len(pk_columns) == 1, table_name
        column_type = pk_columns[0].type
        assert isinstance(column_type, postgresql.UUID), table_name


def test_timestamp_columns_match_design() -> None:
    with_timestamps = {
        "users",
        "api_keys",
        "files",
        "file_identifications",
        "parse_tasks",
        "parse_results",
        "collections",
        "collection_items",
    }
    for table_name in with_timestamps:
        assert "created_at" in Base.metadata.tables[table_name].columns
    for table_name in {"users", "files", "parse_tasks", "collections"}:
        assert "updated_at" in Base.metadata.tables[table_name].columns
    assert "updated_at" in Base.metadata.tables["system_config"].columns
    assert "created_at" not in Base.metadata.tables["system_config"].columns


def test_users_unique_constraint_exists() -> None:
    users = Base.metadata.tables["users"]
    unique_columns = set()
    for constraint in users.constraints:
        if hasattr(constraint, "columns"):
            unique_columns.update(col.name for col in constraint.columns)
    assert "username" in unique_columns


def test_foreign_keys_use_cascade_delete() -> None:
    expected_cascade = {
        ("api_keys", "user_id"),
        ("files", "user_id"),
        ("file_identifications", "file_id"),
        ("parse_tasks", "file_id"),
        ("parse_tasks", "user_id"),
        ("parse_results", "task_id"),
        ("parse_results", "file_id"),
        ("collections", "user_id"),
        ("collection_items", "collection_id"),
        ("collection_items", "user_id"),
        ("collection_items", "task_id"),
        ("collection_items", "file_id"),
    }
    for table_name, column_name in expected_cascade:
        column = Base.metadata.tables[table_name].columns[column_name]
        assert column.foreign_keys, f"{table_name}.{column_name}"
        fk = next(iter(column.foreign_keys))
        assert fk.ondelete == "CASCADE", f"{table_name}.{column_name}"


def test_required_indexes_exist() -> None:
    table_indexes = {
        table_name: {index.name for index in table.indexes}
        for table_name, table in Base.metadata.tables.items()
    }
    expected_indexes = {
        "api_keys": {"ix_api_keys_user_id"},
        "files": {
            "ix_files_user_id",
            "ix_files_status",
            "ix_files_content_type",
            "ix_files_created_at_desc",
            "ix_files_original_name_trgm",
        },
        "file_identifications": {"ix_file_identifications_file_id"},
        "parse_tasks": {
            "ix_parse_tasks_file_id",
            "ix_parse_tasks_user_id",
            "ix_parse_tasks_status",
            "ix_parse_tasks_created_at_desc",
        },
        "parse_results": {
            "ix_parse_results_task_id",
            "ix_parse_results_file_id",
        },
        "collections": {"ix_collections_user_id"},
        "collection_items": {
            "ix_collection_items_collection_id",
            "ix_collection_items_user_id",
            "ix_collection_items_content_type",
            "ix_collection_items_tags",
        },
    }
    for table_name, expected in expected_indexes.items():
        assert expected <= table_indexes[table_name], table_name


def test_files_name_trgm_index_uses_gin_ops() -> None:
    files = Base.metadata.tables["files"]
    index = next(i for i in files.indexes if i.name == "ix_files_original_name_trgm")
    assert index.dialect_options["postgresql"]["using"] == "gin"
    ops = index.dialect_options["postgresql"]["ops"]
    assert ops.get("original_name") == "gin_trgm_ops"


def test_collection_items_tags_uses_gin() -> None:
    items = Base.metadata.tables["collection_items"]
    index = next(i for i in items.indexes if i.name == "ix_collection_items_tags")
    assert index.dialect_options["postgresql"]["using"] == "gin"


def test_all_ddl_compiles_with_postgresql_dialect() -> None:
    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        assert "CREATE TABLE" in str(CreateTable(table).compile(dialect=dialect))
        for index in table.indexes:
            assert "CREATE INDEX" in str(CreateIndex(index).compile(dialect=dialect))


def test_metadata_can_create_mock_engine_schema() -> None:
    engine = create_mock_engine("postgresql://", lambda sql, *args, **kwargs: None)
    Base.metadata.create_all(engine)


@pytest.mark.asyncio
async def test_get_db_commits_and_closes_on_success() -> None:
    session = AsyncMock()
    with patch("app.core.database.AsyncSessionLocal", return_value=session) as factory:
        generator = get_db()
        assert await generator.__anext__() is session
        with pytest.raises(StopAsyncIteration):
            await generator.__anext__()
    factory.assert_called_once_with()
    session.commit.assert_awaited_once()
    session.close.assert_awaited_once()
    session.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_get_db_rolls_back_on_exception() -> None:
    session = AsyncMock()
    with patch("app.core.database.AsyncSessionLocal", return_value=session):
        generator = get_db()
        await generator.__anext__()
        with pytest.raises(RuntimeError, match="boom"):
            await generator.athrow(RuntimeError("boom"))
    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_init_db_creates_all_tables() -> None:
    engine = Mock()
    connection = AsyncMock()
    connection.run_sync = AsyncMock()
    engine.begin.return_value = AsyncMock()
    engine.begin.return_value.__aenter__.return_value = connection
    with patch("app.core.database.async_engine", engine):
        await init_db()
    connection.execute.assert_awaited_once()
    connection.run_sync.assert_awaited_once()


@pytest.mark.asyncio
async def test_init_db_is_idempotent() -> None:
    engine = Mock()
    connection = AsyncMock()
    connection.run_sync = AsyncMock()
    engine.begin.return_value = AsyncMock()
    engine.begin.return_value.__aenter__.return_value = connection
    with patch("app.core.database.async_engine", engine):
        await init_db()
        await init_db()
    assert connection.run_sync.await_count == 2
