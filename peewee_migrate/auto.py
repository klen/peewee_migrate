"""Automatically create migrations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Final, cast

import peewee as pw
from playhouse import postgres_ext  # type: ignore[]
from playhouse.reflection import Column as VanilaColumn

from peewee_migrate.utils import model_fields_gen

if TYPE_CHECKING:
    from .migrator import Migrator
    from .types import TModelType, TParams

INDENT: Final = "    "
NEWLINE: Final = "\n" + INDENT
FIELD_MODULES_MAP: Final = {
    "ArrayField": "pw_pext",
    "BinaryJSONField": "pw_pext",
    "DateTimeTZField": "pw_pext",
    "HStoreField": "pw_pext",
    "IntervalField": "pw_pext",
    "JSONField": "pw_pext",
    "TSVectorField": "pw_pext",
}
PW_MODULES: Final = "playhouse.postgres_ext", "playhouse.fields", "peewee"


def fk_to_params(field: pw.ForeignKeyField) -> TParams:
    """Get params from the given fk."""
    params = {}
    if field.on_delete is not None:
        params["on_delete"] = f"'{field.on_delete}'"

    if field.on_update is not None:
        params["on_update"] = f"'{field.on_update}'"

    return params


def dtf_to_params(field: pw.DateTimeField) -> TParams:
    """Get params from the given datetime field."""
    params = {}
    if not isinstance(field.formats, list):
        params["formats"] = field.formats

    return params


def arrayf_to_params(f: postgres_ext.ArrayField):
    inner_field: pw.Field = f._ArrayField__field
    module = FIELD_MODULES_MAP.get(inner_field.__class__.__name__, "pw")
    return {
        "field_class": f"{module}.{inner_field.__class__.__name__}",
        "field_kwargs": repr(Column(inner_field).get_field_parameters()),
        "dimensions": f.dimensions,
        "convert_values": f.convert_values,
    }


FIELD_TO_PARAMS: dict[type[pw.Field], Callable[[Any], TParams]] = {
    pw.CharField: lambda f: {"max_length": f.max_length},
    pw.DecimalField: lambda f: {
        "auto_round": f.auto_round,
        "decimal_places": f.decimal_places,
        "max_digits": f.max_digits,
        "rounding": f.rounding,
    },
    pw.ForeignKeyField: fk_to_params,
    pw.DateTimeField: dtf_to_params,
    postgres_ext.ArrayField: arrayf_to_params,
}


class Column(VanilaColumn):
    """Get field's migration parameters."""

    field_class: type[pw.Field]

    def __init__(self, field: pw.Field, **kwargs):
        super(Column, self).__init__(
            field.name,
            find_field_type(field),
            field.field_type,
            field.null,
            primary_key=field.primary_key,
            column_name=field.column_name,
            index=field.index,
            unique=field.unique,
            **kwargs,
        )
        self.field = field

        if self.field_class in FIELD_TO_PARAMS:
            if self.extra_parameters is None:  # type: ignore[has-type]
                self.extra_parameters = {}

            self.extra_parameters.update(FIELD_TO_PARAMS[self.field_class](field))

        self.rel_model = None
        self.to_field = None

        if isinstance(field, pw.ForeignKeyField):
            self.to_field = field.rel_field.name
            self.rel_model = (
                "'self'"
                if field.rel_model == field.model
                else "migrator.orm['%s']" % field.rel_model._meta.table_name
            )

    def get_field(self, space: str = " ") -> str:
        """Generate the field definition for this column."""
        field = super(Column, self).get_field()
        module = FIELD_MODULES_MAP.get(self.field_class.__name__, "pw")
        name, _, field = [s and s.strip() for s in field.partition("=")]
        return "{name}{space}={space}{module}.{field}".format(
            name=name, field=field, space=space, module=module
        )

    def get_field_parameters(self, *, change=False) -> TParams:
        """Generate parameters for self field."""
        params = super(Column, self).get_field_parameters()
        params.pop("backref", None)

        if self.field.default is not None and not callable(self.field.default):
            value = self.field.db_value(self.field.default)
            if isinstance(value, pw.WrappedNode):
                params["default"] = str(value.node)
            else:
                params["default"] = repr(value)

        if change:
            params["null"] = self.nullable
            params["unique"] = bool(params.pop("unique", False))
            params["index"] = bool(params.pop("index", False)) or params["unique"]

            params.pop("default", None)
            params.pop("on_delete", None)
            params.pop("on_update", None)

        return params


def diff_model(model: TModelType, source: TModelType, **opts) -> list[str]:
    """Find difference between given peewee models."""
    if model._meta.table_name != source._meta.table_name:  # type: ignore[]
        raise ValueError("Cannot diff models with different table names")  # noqa: EM101, TRY003

    return [*diff_model_fields(model, source, **opts), *diff_model_indexes(model, source)]


def diff_model_fields(model: TModelType, source: TModelType, **opts) -> list[str]:
    changes = []

    model_fields = {f.name for f in model._meta.sorted_fields}  # type: ignore[]
    source_fields = {f.name for f in source._meta.sorted_fields}  # type: ignore[]

    # Add fields
    fields_to_add = model_fields - source_fields
    if fields_to_add:
        fields = list(model_fields_gen(model, *fields_to_add))
        changes.append(create_fields(model, *fields, **opts))

    # Drop fields
    fields_to_remove = source_fields - model_fields
    if fields_to_remove:
        fields = list(model_fields_gen(source, *fields_to_remove))
        changes.append(drop_fields(model, *fields))

    # Change fields
    fields_to_change = model_fields - fields_to_add - fields_to_remove
    source_fields_map = source._meta.fields  # type: ignore[]
    for field in model_fields_gen(model, *fields_to_change):
        source_field = source_fields_map[field.name]  # type: ignore[]
        diff = compare_fields(field, source_field)
        if diff:
            changes.append(change_fields(model, (field, diff)))
            null = diff.pop("null", None)
            if null is not None:
                changes.append(change_not_null(model, field.name, null=null))

    return changes


def diff_model_indexes(model: TModelType, source: TModelType) -> list[str]:
    changes: list[str] = []

    model_indexes = model._meta.fields_to_index()  # type: ignore[]
    source_indexes = source._meta.fields_to_index()  # type: ignore[]

    model_indexes_names = {idx._name for idx in model_indexes}  # type: ignore[]
    source_indexes_names = {idx._name for idx in source_indexes}  # type: ignore[]

    # Drop indexes
    indexes_to_drop = source_indexes_names - model_indexes_names
    for name in sorted(indexes_to_drop):
        changes.append(  # noqa: PERF401
            drop_index(next(idx for idx in source_indexes if idx._name == name))
        )

    # Add indexes
    indexes_to_add = model_indexes_names - source_indexes_names
    for name in sorted(indexes_to_add):
        changes.append(  # noqa: PERF401
            add_index(next(idx for idx in model_indexes if idx._name == name))
        )

    # Change indexes
    indexes_to_check = model_indexes_names & source_indexes_names
    for name in sorted(indexes_to_check):
        idx1 = next(idx for idx in model_indexes if idx._name == name)
        idx2 = next(idx for idx in source_indexes if idx._name == name)
        if idx1._unique != idx2._unique or sorted(idx1._expressions) != sorted(idx2._expressions):
            changes.append(drop_index(idx2))
            changes.append(add_index(idx1))

    return changes


def diff_many(
    active: list[TModelType],
    source: list[TModelType],
    migrator: Migrator | None = None,
    *,
    reverse=False,
) -> list[str]:
    """Calculate changes for migrations from models2 to models1."""
    active = cast("list[TModelType]", pw.sort_models(active))  # type: ignore[]
    source = cast("list[TModelType]", pw.sort_models(source))  # type: ignore[]

    if reverse:
        active = list(reversed(active))
        source = list(reversed(source))

    active_map = {cast("str", m._meta.table_name): m for m in active}  # type: ignore[]
    source_map = {cast("str", m._meta.table_name): m for m in source}  # type: ignore[]

    changes: list[str] = []

    for name, model in active_map.items():
        if name not in source_map:
            continue
        changes.extend(diff_model(model, source_map[name], migrator=migrator))

    # Add models
    changes.extend(
        create_model(active_map[name], migrator=migrator)
        for name in [m for m in active_map if m not in source_map]
    )

    # Remove models
    changes.extend(
        remove_model(source_map[name]) for name in [m for m in source_map if m not in active_map]
    )

    return changes


def model_to_code(model_type: TModelType, **kwargs) -> str:
    """Generate migrations for the given model."""
    template = "class {classname}(pw.Model):\n{fields}\n\n{meta}"
    meta = model_type._meta  # type: ignore[]
    fields = INDENT + NEWLINE.join(
        [
            field_to_code(field, **kwargs)
            for field in meta.sorted_fields
            if not (isinstance(field, pw.PrimaryKeyField) and field.name == "id")
        ]
    )
    meta = INDENT + NEWLINE.join(
        filter(
            None,
            [
                "class Meta:",
                f'{INDENT}table_name = "{meta.table_name}"',
                f'{INDENT}schema = "{meta.schema}"' if meta.schema else "",
                (
                    f"{INDENT}primary_key = pw.CompositeKey{meta.primary_key.field_names!r}"
                    if isinstance(meta.primary_key, pw.CompositeKey)
                    else ""
                ),
                f"{INDENT}indexes = {meta.indexes!r}" if meta.indexes else "",
            ],
        )
    )

    return template.format(classname=model_type.__name__, fields=fields, meta=meta)


def create_model(model_type: TModelType, **kwargs) -> str:
    """Generate migrations to create model."""
    return "@migrator.create_model\n" + model_to_code(model_type, **kwargs)


def remove_model(model_type: TModelType, **kwargs) -> str:
    """Generate migrations to remove model."""
    meta = model_type._meta  # type: ignore[]
    return "migrator.remove_model('%s')" % meta.table_name


def create_fields(model_type: TModelType, *fields: pw.Field, **kwargs) -> str:
    """Generate migrations to add fields."""
    meta = model_type._meta  # type: ignore[]
    return "migrator.add_fields(%s'%s', %s)" % (
        NEWLINE,
        meta.table_name,
        NEWLINE
        + ("," + NEWLINE).join([field_to_code(field, space=False, **kwargs) for field in fields]),
    )


def drop_fields(model_type: TModelType, *fields: pw.Field | str) -> str:
    """Generate migrations to remove fields."""
    meta = model_type._meta  # type: ignore[]
    fields = tuple(
        repr(field.name) if isinstance(field, pw.Field) else repr(field) for field in fields
    )
    return "migrator.remove_fields('%s', %s)" % (meta.table_name, ", ".join(fields))


def field_to_code(field: pw.Field, *, space: bool = True, **kwargs) -> str:
    """Generate field description."""
    col = Column(field)
    return col.get_field(" " if space else "")


def compare_fields(field1: pw.Field, field2: pw.Field) -> dict:
    """Find diffs between the given fields."""
    ftype1, ftype2 = find_field_type(field1), find_field_type(field2)
    if ftype1 != ftype2:
        return {"type": True}

    col1, col2 = (
        Column(field1, extra_parameters={"index": field1.index, "unique": field1.unique}),
        Column(field2, extra_parameters={"index": field2.index, "unique": field2.unique}),
    )
    params1, params2 = (
        col1.get_field_parameters(change=True),
        col2.get_field_parameters(change=True),
    )
    return dict(set(params1.items()) - set(params2.items()))


def change_fields(model_cls: TModelType, *fields: pw.Tuple[pw.Field, dict]) -> str:
    """Generate migrations to change fields."""
    meta = model_cls._meta  # type: ignore[]
    return "migrator.change_fields('%s', %s)" % (
        meta.table_name,
        ("," + NEWLINE).join([field_to_code(f, space=False) for f, diff in fields]),
    )


def change_not_null(model_type: TModelType, name: str, *, null: bool) -> str:
    """Generate migrations."""
    meta = model_type._meta  # type: ignore[]
    operation = "drop_not_null" if null else "add_not_null"
    return "migrator.%s('%s', %s)" % (operation, meta.table_name, repr(name))


def add_index(idx: pw.ModelIndex) -> str:
    """Generate migrations."""
    meta = idx._model._meta  # type: ignore[]
    unique = idx._unique  # type: ignore[]
    fields = idx._expressions  # type: ignore[]
    names = ", ".join(f"'{f.name}'" for f in fields)
    return f"migrator.add_index('{meta.table_name}', {names}, unique={unique})"


def drop_index(idx: pw.ModelIndex) -> str:
    """Generate migrations."""
    meta = idx._model._meta  # type: ignore[]
    fields = idx._expressions  # type: ignore[]
    names = ", ".join(f"'{f.name}'" for f in fields)
    return f"migrator.drop_index('{meta.table_name}', {names})"


def find_field_type(field: pw.Field) -> type[pw.Field]:
    ftype = type(field)
    if ftype.__module__ not in PW_MODULES:
        for cls in ftype.mro():
            if cls.__module__ in PW_MODULES:
                return cls

    return ftype
