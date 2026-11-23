from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    import peewee as pw

    from peewee_migrate.types import TModelType


def model_fields_gen(model: TModelType, *names: str) -> Iterator[pw.Field]:
    """Get model fields by names.

    Args:
        model (pw.Model): Peewee model.
        *names (str): Field names.

    Returns:
        list: List of fields.
    """
    meta = model._meta
    for field in meta.sorted_fields:
        if field.name in names:
            yield field
