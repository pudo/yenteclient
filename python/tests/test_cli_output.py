"""Tests for the CLI output formatters (json / jsonl / table)."""

import json
import sys
from io import StringIO

from pydantic import BaseModel

from yente_client.cli.output import Format, print_json, print_jsonl, resolve_format, to_jsonable


class _Sample(BaseModel):
    name: str
    score: float


def test_to_jsonable_on_pydantic_model() -> None:
    obj = to_jsonable(_Sample(name="x", score=0.92))
    assert obj == {"name": "x", "score": 0.92}


def test_to_jsonable_passthrough() -> None:
    assert to_jsonable({"a": 1}) == {"a": 1}
    assert to_jsonable([1, 2, 3]) == [1, 2, 3]


def test_print_json_pretty(capsys) -> None:
    print_json({"a": 1, "b": [2, 3]})
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed == {"a": 1, "b": [2, 3]}
    # Pretty formatting → multiple lines.
    assert "\n" in out


def test_print_json_emits_pydantic_via_to_jsonable(capsys) -> None:
    print_json(_Sample(name="Person", score=0.5))
    parsed = json.loads(capsys.readouterr().out)
    assert parsed == {"name": "Person", "score": 0.5}


def test_print_jsonl_one_per_line(capsys) -> None:
    print_jsonl([{"id": "Q1"}, {"id": "Q2"}, {"id": "Q3"}])
    lines = capsys.readouterr().out.strip().split("\n")
    assert len(lines) == 3
    assert [json.loads(line) for line in lines] == [{"id": "Q1"}, {"id": "Q2"}, {"id": "Q3"}]


def test_resolve_format_explicit_wins() -> None:
    assert resolve_format(Format.JSON) == Format.JSON
    assert resolve_format(Format.JSONL) == Format.JSONL
    assert resolve_format(Format.TABLE) == Format.TABLE


def test_resolve_format_auto_pipe_becomes_json(monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdout", StringIO())  # no isatty()
    assert resolve_format(Format.AUTO) == Format.JSON


def test_resolve_format_auto_tty_becomes_table(monkeypatch) -> None:
    class _TtyStdout:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdout", _TtyStdout())
    assert resolve_format(Format.AUTO) == Format.TABLE
