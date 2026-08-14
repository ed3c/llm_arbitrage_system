from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes
from llm_arbitrage_system.experiments.strict_yaml import strict_yaml_load

_SWEEP_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class WalkForwardSpec:
    train_size: int
    test_size: int
    step_size: int
    purge_size: int = 0
    anchored: bool = False
    minimum_windows: int = 1

    def __post_init__(self) -> None:
        if self.train_size < 1 or self.test_size < 1 or self.step_size < 1:
            raise ValueError("train_size, test_size, and step_size must be positive")
        if self.purge_size < 0:
            raise ValueError("purge_size cannot be negative")
        if self.minimum_windows < 1:
            raise ValueError("minimum_windows must be positive")


@dataclass(frozen=True, slots=True)
class SweepSpec:
    parameters: Mapping[str, tuple[Any, ...]]
    walk_forward: WalkForwardSpec
    maximum_candidates: int = 256

    def __post_init__(self) -> None:
        if not self.parameters:
            raise ValueError("parameter sweep must contain at least one axis")
        if self.maximum_candidates < 1 or self.maximum_candidates > 4096:
            raise ValueError("maximum_candidates must be in [1, 4096]")
        for name, values in self.parameters.items():
            if "." not in name:
                raise ValueError(f"sweep parameter must be section.field: {name}")
            if not values:
                raise ValueError(f"sweep parameter has no values: {name}")


def load_sweep_spec(path: Path) -> SweepSpec:
    resolved = path.resolve()
    try:
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"{resolved}: sweep file is not readable UTF-8") from error
    try:
        parsed = strict_yaml_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"{resolved}: invalid sweep YAML: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("sweep configuration must be a mapping")
    payload = cast(Mapping[str, Any], parsed)
    _reject_unknown(
        payload,
        {"schema_version", "parameters", "walk_forward", "maximum_candidates"},
    )
    if payload.get("schema_version") != _SWEEP_SCHEMA_VERSION:
        raise ValueError("sweep.schema_version must be 1")

    raw_parameters = payload.get("parameters")
    if not isinstance(raw_parameters, dict):
        raise ValueError("sweep.parameters must be a mapping")
    parameters: dict[str, tuple[Any, ...]] = {}
    for name, raw_values in cast(Mapping[str, Any], raw_parameters).items():
        if isinstance(raw_values, (str, bytes)) or not isinstance(raw_values, Sequence):
            raise ValueError(f"sweep axis {name} must be a sequence")
        values = tuple(_sweep_scalar(name, item) for item in raw_values)
        parameters[name] = tuple(sorted(values, key=canonical_json_bytes))

    raw_walk_forward = payload.get("walk_forward")
    if not isinstance(raw_walk_forward, dict):
        raise ValueError("sweep.walk_forward must be a mapping")
    walk = cast(Mapping[str, Any], raw_walk_forward)
    _reject_unknown(
        walk,
        {
            "train_size",
            "test_size",
            "step_size",
            "purge_size",
            "anchored",
            "minimum_windows",
        },
    )
    walk_forward = WalkForwardSpec(
        train_size=_required_integer(walk, "train_size"),
        test_size=_required_integer(walk, "test_size"),
        step_size=_required_integer(walk, "step_size"),
        purge_size=_optional_integer(walk, "purge_size", 0),
        anchored=_optional_boolean(walk, "anchored", False),
        minimum_windows=_optional_integer(walk, "minimum_windows", 1),
    )
    return SweepSpec(
        parameters=parameters,
        walk_forward=walk_forward,
        maximum_candidates=_optional_integer(payload, "maximum_candidates", 256),
    )


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown sweep fields: {', '.join(unknown)}")


def _sweep_scalar(name: str, value: Any) -> Any:
    if value is None or isinstance(value, (dict, list, tuple)):
        raise ValueError(f"sweep axis {name} contains a non-scalar value")
    if not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"sweep axis {name} contains an unsupported value")
    return value


def _required_integer(payload: Mapping[str, Any], key: str) -> int:
    if key not in payload:
        raise ValueError(f"walk_forward.{key} is required")
    return _optional_integer(payload, key, 0)


def _optional_integer(payload: Mapping[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return cast(int, value)


def _optional_boolean(payload: Mapping[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value
