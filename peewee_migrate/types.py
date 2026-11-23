"""Peewee-Migrate custom types."""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any, TypeVar

from peewee import Model

TModelType = type[Model]
TParams = dict[str, Any]

# What `Router.create(auto=...)` accepts: a flag, a module path, an imported module
# or a model class, and a list of those.
TAutoSource = str | ModuleType | TModelType
TAuto = bool | TAutoSource | list[TAutoSource]

TMigration = Callable[..., Any]

TVModelType = TypeVar("TVModelType", bound=TModelType)
