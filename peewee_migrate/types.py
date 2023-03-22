from __future__ import annotations

from typing import Any, Dict, Type, TypeVar, Union

from peewee import Model

TModelType = Type[Model]
TModelArg = Union[TModelType, str]
TParams = Dict[str, Any]

TVModelType = TypeVar("TVModelType", bound=TModelType)
