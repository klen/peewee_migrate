"""Automatically create migrations."""
from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Final,
    Iterable,
    List,
    Optional,
    Type,
    Union,
    cast,
)

import peewee as pw
from playhouse import postgres_ext
from playhouse.reflection import Column as VanilaColumn

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
            "convert_values": f.convert_values
        }


FIELD_TO_PARAMS: Dict[Type[pw.Field], Callable[[Any], TParams]] = {
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

    field_class: Type[pw.Field]

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
        if change:
            params["unique"] = bool(params.pop("unique", False))
            params["index"] = bool(params.pop("index", False)) or params["unique"]
            params.pop("on_delete", None)
            params.pop("on_update", None)
            params["null"] = self.nullable

        if self.field.default is not None and not callable(self.field.default):
            value = self.field.db_value(self.field.default)
            if isinstance(value, pw.WrappedNode):
                params["default"] = str(value.node)
            else:
                params["default"] = repr(value)

        return params


def diff_one(model1: TModelType, model2: TModelType, **kwargs) -> List[str]:  # noqa: C901
    """Find difference between given peewee models."""
    changes = []

    meta1, meta2 = model1._meta, model2._meta  # type: ignore[]
    field_names1 = meta1.fields
    field_names2 = meta2.fields

    # Add fields
    names1 = set(field_names1) - set(field_names2)
    if names1:
        fields = [field_names1[name] for name in names1]
        changes.append(create_fields(model1, *fields, **kwargs))

    # Drop fields
    names2 = set(field_names2) - set(field_names1)
    if names2:
        changes.append(drop_fields(model1, *names2))

    # Change fields
    fields_to_change = []
    fields_nulls = []
    fields_indexes = []
    for name in set(field_names1) - names1 - names2:
        field1, field2 = field_names1[name], field_names2[name]
        diff = compare_fields(field1, field2)
        null = diff.pop("null", None)
        index = diff.pop("index", None)
        unique = diff.pop("unique", None)

        if diff:
            fields_to_change.append((field1, diff))

        if null is not None:
            fields_nulls.append((name, null))

        if (index is not None) or (unique is not None):
            fields_indexes.append((name, index, unique))

    if fields_to_change:
        changes.append(change_fields(model1, *fields_to_change))

    for name, null in fields_nulls:
        changes.append(change_not_null(model1, name, null=null))

    for name, index, unique in fields_indexes:
        if (index is True) or (unique is True):
            if field_names2[name].unique or field_names2[name].index:
                changes.append(drop_index(model1, name))
            changes.append(add_index(model1, name, unique=unique))
        else:
            changes.append(drop_index(model1, name))

    # Check additional compound indexes
    indexes1 = meta1.indexes
    indexes2 = meta2.indexes

    # Drop compound indexes
    indexes_to_drop = set(indexes2) - set(indexes1)
    changes.extend(
        drop_index(model1, name=index[0])
        for index in indexes_to_drop
        if isinstance(index[0], (list, tuple)) and len(index[0]) > 1
    )

    # Add compound indexes
    indexes_to_add = set(indexes1) - set(indexes2)
    changes.extend(
        add_index(model1, name=index[0], unique=index[1])
        for index in indexes_to_add
        if isinstance(index[0], (list, tuple)) and len(index[0]) > 1
    )

    return changes


def diff_many(
    models1: List[TModelType],
    models2: List[TModelType],
    migrator: Optional[Migrator] = None,
    *,
    reverse=False,
) -> List[str]:
    """Calculate changes for migrations from models2 to models1."""
    models1 = cast(List["TModelType"], pw.sort_models(models1))  # type: ignore[]
    models2 = cast(List["TModelType"], pw.sort_models(models2))  # type: ignore[]

    if reverse:
        models1 = list(reversed(models1))
        models2 = list(reversed(models2))

    models_map1 = {cast(str, m._meta.table_name): m for m in models1}  # type: ignore[]
    models_map2 = {cast(str, m._meta.table_name): m for m in models2}  # type: ignore[]

    changes: List[str] = []

    for name, model1 in models_map1.items():
        if name not in models_map2:
            continue
        changes.extend(diff_one(model1, models_map2[name], migrator=migrator))

    # Add models
    changes.extend(
        create_model(models_map1[name], migrator=migrator)
        for name in [m for m in models_map1 if m not in models_map2]
    )

    # Remove models
    changes.extend(
        remove_model(models_map2[name]) for name in [m for m in models_map2 if m not in models_map1]
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


def drop_fields(model_type: TModelType, *fields: pw.Field, **kwargs) -> str:
    """Generate migrations to remove fields."""
    meta = model_type._meta  # type: ignore[]
    return "migrator.remove_fields('%s', %s)" % (
        meta.table_name,
        ", ".join(map(repr, fields)),
    )


def field_to_code(field: pw.Field, *, space: bool = True, **kwargs) -> str:
    """Generate field description."""
    col = Column(field)
    return col.get_field(" " if space else "")


def compare_fields(field1: pw.Field, field2: pw.Field) -> Dict:
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


def change_fields(model_cls: TModelType, *fields: pw.Tuple[pw.Field, Dict]) -> str:
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


def add_index(model_type: TModelType, name: Union[str, Iterable[str]], *, unique: bool) -> str:
    """Generate migrations."""
    meta = model_type._meta  # type: ignore[]
    columns = repr(name).strip("()[]")
    return f"migrator.add_index('{meta.table_name}', {columns}, unique={unique})"


def drop_index(model_type: TModelType, name: Union[str, Iterable[str]]) -> str:
    """Generate migrations."""
    meta = model_type._meta  # type: ignore[]
    columns = repr(name).strip("()[]")
    return f"migrator.drop_index('{meta.table_name}', {columns})"


def find_field_type(field: pw.Field) -> Type[pw.Field]:
    ftype = type(field)
    if ftype.__module__ not in PW_MODULES:
        for cls in ftype.mro():
            if cls.__module__ in PW_MODULES:
                return cls

    return ftype
