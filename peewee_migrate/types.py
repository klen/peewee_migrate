"""Peewee-Migrate custom types."""

from __future__ import annotations

from typing import Any, Dict, Type, TypeVar

from peewee import Model

TModelType = Type[Model]
TParams = Dict[str, Any]

TVModelType = TypeVar("TVModelType", bound=TModelType)
