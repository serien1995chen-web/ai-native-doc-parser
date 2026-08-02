"""Unit tests for the parser protocol and registry."""

from __future__ import annotations

from typing import Any

import pytest
from app.parsers import BaseParser, ParseResult, ParserInfo, ParserRegistry

pytestmark = pytest.mark.unit


class StubParser(BaseParser):
    """Concrete parser used for protocol tests."""

    def __init__(
        self,
        name: str = "stub",
        supported_types: list[str] | None = None,
        version: str = "1.0",
    ) -> None:
        self._info = ParserInfo(
            name=name,
            supported_types=supported_types or [],
            required_gpu=False,
            required_models=[],
            version=version,
        )

    def info(self) -> ParserInfo:
        return self._info

    def parse(
        self,
        file_path: str,
        options: dict[str, Any] | None = None,
    ) -> ParseResult:
        return ParseResult(markdown="parsed", json_data={"source": file_path})


class IncompleteParser(BaseParser):
    """Parser that does not implement the abstract interface."""


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    """Reset the class-level registry before each test."""
    ParserRegistry._parsers.clear()
    yield
    ParserRegistry._parsers.clear()


def test_parse_result_required_fields_and_defaults() -> None:
    result = ParseResult(markdown="# title", json_data={"key": "value"})
    assert result.markdown == "# title"
    assert result.json_data == {"key": "value"}
    assert result.page_count is None
    assert result.processing_time_ms is None


def test_parser_info_has_all_five_fields() -> None:
    info = ParserInfo(
        name="pdf",
        supported_types=["pdf"],
        required_gpu=True,
        required_models=["doclayout-yolo"],
        version="1.0.0",
    )
    assert info.name == "pdf"
    assert info.supported_types == ["pdf"]
    assert info.required_gpu is True
    assert info.required_models == ["doclayout-yolo"]
    assert info.version == "1.0.0"


def test_base_parser_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseParser()


def test_subclass_implementing_abstract_methods_is_instantiable() -> None:
    parser = StubParser()
    assert isinstance(parser, BaseParser)


def test_subclass_missing_abstract_methods_is_not_instantiable() -> None:
    with pytest.raises(TypeError):
        IncompleteParser()


def test_estimate_returns_default_resource_estimate() -> None:
    parser = StubParser()
    assert parser.estimate("/tmp/file.pdf") == {"estimated_seconds": 0, "gpu_memory_mb": 0}


def test_register_maps_every_supported_type_to_same_instance() -> None:
    parser = StubParser(supported_types=["pdf", "docx"])
    ParserRegistry.register(parser)
    assert ParserRegistry.get_parser("pdf") is parser
    assert ParserRegistry.get_parser("docx") is parser


def test_get_parser_returns_none_for_unregistered_type() -> None:
    assert ParserRegistry.get_parser("unknown") is None


def test_list_parsers_deduplicates_same_instance() -> None:
    parser = StubParser(supported_types=["pdf", "docx"])
    ParserRegistry.register(parser)
    infos = ParserRegistry.list_parsers()
    assert len(infos) == 1
    assert infos[0] == parser.info()


def test_public_interfaces_importable_from_package() -> None:
    assert BaseParser is not None
    assert ParseResult is not None
    assert ParserInfo is not None
    assert ParserRegistry is not None


def test_later_registration_overwrites_earlier_for_same_type() -> None:
    first = StubParser(name="first", supported_types=["pdf"])
    second = StubParser(name="second", supported_types=["pdf"])
    ParserRegistry.register(first)
    ParserRegistry.register(second)
    assert ParserRegistry.get_parser("pdf") is second


def test_register_with_empty_supported_types_leaves_no_mapping() -> None:
    parser = StubParser()
    ParserRegistry.register(parser)
    assert ParserRegistry.get_parser("anything") is None


def test_list_parsers_deduplicates_shared_supported_types() -> None:
    first = StubParser(name="first", supported_types=["pdf", "html"])
    second = StubParser(name="second", supported_types=["pdf", "txt"])
    ParserRegistry.register(first)
    ParserRegistry.register(second)
    infos = ParserRegistry.list_parsers()
    assert len(infos) == 2
    names = {info.name for info in infos}
    assert names == {"first", "second"}


def test_parse_without_options_returns_valid_result() -> None:
    result = StubParser().parse("/tmp/a.pdf")
    assert result.markdown == "parsed"
    assert result.json_data == {"source": "/tmp/a.pdf"}


def test_list_parsers_returns_empty_list_when_unregistered() -> None:
    assert ParserRegistry.list_parsers() == []
