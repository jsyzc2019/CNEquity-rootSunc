"""Modules other repositories import must not be pruned as dead code.

A module that only this repository's tests reference can still be a public
contract: EquityLab imports ``security_identifiers`` from its backtest ledger,
dataset canonicalization and research samplers, and hashes the module source
as part of frozen sample identities.  Deleting it in 0.18.0 made EquityLab
unimportable.  Removing or renaming anything listed here needs a deprecation
cycle and a changelog entry, not a dead-code sweep.
"""

import importlib
from pathlib import Path

import pytest

DOWNSTREAM_IMPORTS = {
    "cnequity.domain.security_identifiers": (
        "SecurityIdentifierChange",
        "canonical_symbol",
        "canonicalize_dated_identifiers",
        "identifier_aliases",
        "identifier_changes",
        "transitions_on",
    ),
}


@pytest.mark.parametrize("module_name", sorted(DOWNSTREAM_IMPORTS))
def test_downstream_imported_names_exist(module_name):
    module = importlib.import_module(module_name)
    missing = [name for name in DOWNSTREAM_IMPORTS[module_name] if not hasattr(module, name)]
    assert missing == []


def test_identifier_registry_source_is_hashable():
    """EquityLab binds frozen samples to the bytes of this file."""
    module = importlib.import_module("cnequity.domain.security_identifiers")
    assert Path(module.__file__).is_file()
    assert module.identifier_changes()
