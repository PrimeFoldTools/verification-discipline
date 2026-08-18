"""Fixture-first tests — network-free, no private state. Run: `make test`.

Every test uses a fake client or an injected record set, so the whole gate runs
without any external store. The point each test pins is named in its docstring.
"""
from __future__ import annotations

import json

import pytest

import cli
import gate
from json_safe import dumps


class FakeClient:
    """In-memory stand-in for the store. Records creates, attaches, receipts."""

    def __init__(self, existing=None, unavailable=False):
        self._existing = existing or []
        self._unavailable = unavailable
        self.created, self.attached, self.receipts = [], [], []

    def read_existing(self):
        if self._unavailable:
            raise gate.StoreUnavailable("store 503")
        return self._existing

    def create(self, record):
        self.created.append(record)
        return f"id-{len(self.created)}"

    def attach(self, page_id, note):
        self.attached.append((page_id, note))

    def receipt(self, entry):
        self.receipts.append(entry)


# ------------------------------------------------------------- exit-code contract

@pytest.mark.parametrize("client_kw,expected_outcome,expected_code", [
    (dict(), "created", 0),
    (dict(unavailable=True), "created_fail_open", 3),   # UNCHECKED create -> 3, not 0
])
def test_exit_codes(client_kw, expected_outcome, expected_code, capsys):
    c = FakeClient(**client_kw)
    code = cli.run(["--title", "sample record 4210 alpha"], client=c)
    out = json.loads(capsys.readouterr().out.strip())
    assert out["outcome"] == expected_outcome
    assert code == expected_code


def test_fail_open_is_not_a_silent_zero():
    c = FakeClient(unavailable=True)
    assert cli.run(["--title", "must not be lost 42"], client=c) == 3
    assert len(c.created) == 1                    # created ANYWAY
    assert c.receipts[0]["action"] == "created_fail_open" and c.receipts[0]["error"]


def test_empty_title_rejected_exit_1(capsys):
    assert cli.run(["--title", "   "], client=FakeClient()) == 1
    assert "non-empty" in capsys.readouterr().out


def test_dry_run_writes_nothing():
    c = FakeClient()
    assert cli.run(["--title", "peek 7", "--dry-run"], client=c) == 0
    assert c.created == [] and c.receipts == []


# ---------------------------------------------------------------- gate behaviour

def test_create_leaves_a_receipt():
    c = FakeClient()
    out = gate.submit({"title": "monthly export batch 3200"}, client=c)
    assert out["outcome"] == "created" and out["receipt"] is True
    assert c.receipts[0]["action"] == "created"


def test_duplicate_attaches_instead_of_creating():
    existing = [{"id": "canon-1", "title": "quarterly report section 7 draft"}]
    c = FakeClient(existing=existing)
    out = gate.submit({"title": "quarterly report section 7 revision"}, client=c)
    assert out["outcome"] == "attached" and out["id"] == "canon-1"
    assert c.created == [] and len(c.attached) == 1


def test_no_specific_dimension_never_merges():
    # Same tokens, but neither carries a digit/specific dimension -> kept distinct.
    existing = [{"id": "x", "title": "widget catalog dashboard view"}]
    c = FakeClient(existing=existing)
    out = gate.submit({"title": "widget catalog dashboard summary"}, client=c)
    assert out["outcome"] == "created"           # NOT merged


# --------------------------------------------------------- the numpy-bool guard

def test_json_safe_refuses_to_stringify_a_fake_false():
    class FakeBool:
        # mimics numpy.bool_(False): truthy-looking str(), native via .item()
        def __str__(self): return "False"
        def item(self): return False
    payload = {"pass": FakeBool()}
    # default=str would emit "False" (truthy). dumps() must emit native false.
    assert json.loads(dumps(payload))["pass"] is False
