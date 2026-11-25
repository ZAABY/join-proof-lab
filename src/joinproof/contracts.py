"""Strict, versioned input contracts. No SQL or expression evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ContractError(ValueError):
    """The contract is ambiguous or unsupported."""


def _object(value, required, optional=()):
    if not isinstance(value, dict):
        raise ContractError("Expected a JSON object")
    missing = set(required) - value.keys()
    unknown = value.keys() - set(required) - set(optional)
    if missing or unknown:
        raise ContractError(f"Missing fields {sorted(missing)}; unknown fields {sorted(unknown)}")


def _name(value):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ContractError("Names must be nonempty strings of at most 128 characters")
    return value


def _names(value, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ContractError("Expected a nonempty list of column names")
    result = tuple(_name(v) for v in value)
    if len(set(result)) != len(result):
        raise ContractError("Column names may not repeat")
    return result


@dataclass(frozen=True)
class Measure:
    name: str
    column: str
    scale: int
    conserve: bool


@dataclass(frozen=True)
class Relation:
    name: str
    path: Path
    key: tuple[str, ...]
    grain: tuple[str, ...]
    measures: tuple[Measure, ...]
    join: str
    key_unique: bool


@dataclass(frozen=True)
class Contract:
    relations: tuple[Relation, ...]
    preserve_root_rows: bool
    _raw_json: str

    @property
    def raw(self) -> dict:
        """Return a fresh copy so caller mutations cannot change the audit identity."""
        return json.loads(self._raw_json)


def parse_contract(value: dict, base: Path) -> Contract:
    _object(value, ("version", "relations", "preserve_root_rows"))
    if type(value["version"]) is not int or value["version"] != 1:
        raise ContractError("Only contract version 1 is supported")
    if type(value["preserve_root_rows"]) is not bool:
        raise ContractError("preserve_root_rows must be boolean")
    if not isinstance(value["relations"], list) or not value["relations"]:
        raise ContractError("At least a root relation is required")
    if len(value["relations"]) > 32:
        raise ContractError("At most 32 relations are supported")
    relations = []
    for index, item in enumerate(value["relations"]):
        _object(item, ("name", "path", "key", "grain", "measures", "join", "key_unique"))
        name = _name(item["name"])
        if "." in name:
            raise ContractError("Relation names cannot contain periods")
        file = _name(item["path"])
        path = (base / file).resolve()
        if not path.is_relative_to(base.resolve()):
            raise ContractError("CSV paths must stay within the contract directory")
        if path.suffix.lower() != ".csv":
            raise ContractError("Only CSV input files are supported")
        key = _names(item["key"])
        grain = _names(item["grain"], allow_empty=True)
        if item["join"] not in (("root",) if index == 0 else ("left", "inner")):
            raise ContractError("First relation must be root; children must be left or inner")
        if type(item["key_unique"]) is not bool:
            raise ContractError("key_unique must be boolean")
        if not isinstance(item["measures"], list):
            raise ContractError("measures must be a list")
        measures = []
        for m in item["measures"]:
            _object(m, ("name", "column", "scale", "conserve"))
            mn = _name(m["name"])
            if "." in mn:
                raise ContractError("Measure names cannot contain periods")
            if type(m["scale"]) is not int or not 0 <= m["scale"] <= 9:
                raise ContractError("Measure scale must be an integer from 0 to 9")
            if type(m["conserve"]) is not bool:
                raise ContractError("Measure conserve must be boolean")
            measures.append(Measure(mn, _name(m["column"]), m["scale"], m["conserve"]))
        if len({m.name for m in measures}) != len(measures):
            raise ContractError("Measure names must be unique within each relation")
        relations.append(
            Relation(name, path, key, grain, tuple(measures), item["join"], item["key_unique"])
        )
    if len({r.name for r in relations}) != len(relations):
        raise ContractError("Relation names must be unique")
    if len({len(r.key) for r in relations}) != 1:
        raise ContractError("All root/child key tuples must have the same arity")
    return Contract(
        tuple(relations), value["preserve_root_rows"], json.dumps(value, sort_keys=True)
    )


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ContractError(f"Repeated JSON field: {key}")
        value[key] = item
    return value


def load_contract(path: Path) -> Contract:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, ValueError) as exc:
        raise ContractError(f"Cannot read contract: {exc}") from exc
    return parse_contract(value, path.parent)
