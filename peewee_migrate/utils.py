from peewee_migrate.types import TModelType


def model_fields_gen(model: TModelType, *names: str):
    """Get model fields by names.

    Args:
        model (pw.Model): Peewee model.
        *names (str): Field names.

    Returns:
        list: List of fields.
    """
    meta = model._meta  # type: ignore[]
    for field in meta.sorted_fields:
        if field.name in names:
            yield field
