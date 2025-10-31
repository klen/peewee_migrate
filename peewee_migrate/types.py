"""Peewee-Migrate custom types."""

from __future__ import annotations

from typing import Any, TypeVar

from peewee import Model

TModelType = type[Model]
TParams = dict[str, Any]

TVModelType = TypeVar("TVModelType", bound=TModelType)
