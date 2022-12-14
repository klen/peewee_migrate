"""Automatically create migrations."""

from collections import OrderedDict
from collections.abc import Hashable, Iterable
from typing import Dict, List, Type, Union

import peewee as pw
from playhouse.reflection import Column as VanilaColumn

INDENT = "    "
NEWLINE = "\n" + INDENT
FIELD_MODULES_MAP = {
    "ArrayField": "pw_pext",
    "BinaryJSONField": "pw_pext",
    "DateTimeTZField": "pw_pext",
    "HStoreField": "pw_pext",
    "IntervalField": "pw_pext",
    "JSONField": "pw_pext",
    "TSVectorField": "pw_pext",
}
PW_MODULES = "peewee", "playhouse.postgres_ext", "playhouse.fields"


def fk_to_params(field: pw.ForeignKeyField) -> Dict:
    """Get params from the given fk."""
    params = {}
    if field.on_delete is not None:
        params["on_delete"] = f"'{field.on_delete}'"

    if field.on_update is not None:
        params["on_update"] = f"'{field.on_update}'"

    return params


def dtf_to_params(field: pw.DateTimeField) -> Dict:
    """Get params from the given datetime field."""
    params = {}
    if not isinstance(field.formats, list):
        params["formats"] = field.formats

    return params


FIELD_TO_PARAMS = {
    pw.CharField: lambda f: {"max_length": f.max_length},
    pw.DecimalField: lambda f: {
        "max_digits": f.max_digits,
        "decimal_places": f.decimal_places,
        "auto_round": f.auto_round,
        "rounding": f.rounding,
    },
    pw.ForeignKeyField: fk_to_params,
    pw.DateTimeField: dtf_to_params,
}


class Column(VanilaColumn):
    """Get field's migration parameters."""

    field_class: Type[pw.Field]

    def __init__(self, field: pw.Field, **kwargs):  # noqa
        super(Column, self).__init__(
            field.name,
            find_field_type(field),
            field.field_type,
            field.null,
            primary_key=field.primary_key,
            column_name=field.column_name,
            index=field.index,
            unique=field.unique,
            extra_parameters={},
        )
        if field.default is not None and not callable(field.default):
            self.default = repr(field.default)

        if self.field_class in FIELD_TO_PARAMS:
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

    def get_field_parameters(self) -> Dict:
        """Generate parameters for self field."""
        params = super(Column, self).get_field_parameters()
        if self.default is not None:
            params["default"] = self.default
        return params


def diff_one(model1: pw.Model, model2: pw.Model, **kwargs) -> List[str]:
    """Find difference between given peewee models."""
    changes = []

    field_names1 = model1._meta.fields
    field_names2 = model2._meta.fields

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
    fields_ = []
    nulls_ = []
    indexes_ = []
    for name in set(field_names1) - names1 - names2:
        field1, field2 = field_names1[name], field_names2[name]
        diff = compare_fields(field1, field2)
        null = diff.pop("null", None)
        index = diff.pop("index", None)

        if diff:
            fields_.append(field1)

        if null is not None:
            nulls_.append((name, null))

        if index is not None:
            indexes_.append((name, index[0], index[1]))

    if fields_:
        changes.append(change_fields(model1, *fields_, **kwargs))

    for name, null in nulls_:
        changes.append(change_not_null(model1, name, null))

    for name, index, unique in indexes_:
        if index is True or unique is True:
            if field_names2[name].unique or field_names2[name].index:
                changes.append(drop_index(model1, name))
            changes.append(add_index(model1, name, unique))
        else:
            changes.append(drop_index(model1, name))

    # Check additional compound indexes
    indexes1 = model1._meta.indexes
    indexes2 = model2._meta.indexes

    # Drop compound indexes
    indexes_to_drop = set(indexes2) - set(indexes1)
    for index in indexes_to_drop:
        if isinstance(index[0], (list, tuple)) and len(index[0]) > 1:
            changes.append(drop_index(model1, name=index[0]))

    # Add compound indexes
    indexes_to_add = set(indexes1) - set(indexes2)
    for index in indexes_to_add:
        if isinstance(index[0], (list, tuple)) and len(index[0]) > 1:
            changes.append(add_index(model1, name=index[0], unique=index[1]))

    return changes


def diff_many(models1, models2, migrator=None, reverse=False):
    """Calculate changes for migrations from models2 to models1."""
    models1 = pw.sort_models(models1)
    models2 = pw.sort_models(models2)

    if reverse:
        models1 = reversed(models1)
        models2 = reversed(models2)

    models1 = OrderedDict([(m._meta.table_name, m) for m in models1])
    models2 = OrderedDict([(m._meta.table_name, m) for m in models2])

    changes = []

    for name, model1 in models1.items():
        if name not in models2:
            continue
        changes += diff_one(model1, models2[name], migrator=migrator)

    # Add models
    for name in [m for m in models1 if m not in models2]:
        changes.append(create_model(models1[name], migrator=migrator))

    # Remove models
    for name in [m for m in models2 if m not in models1]:
        changes.append(remove_model(models2[name]))

    return changes


def model_to_code(Model: pw.Model, **kwargs) -> str:
    """Generate migrations for the given model."""
    template = """class {classname}(pw.Model):
{fields}

{meta}
"""
    fields = INDENT + NEWLINE.join(
        [
            field_to_code(field, **kwargs)
            for field in Model._meta.sorted_fields
            if not (isinstance(field, pw.PrimaryKeyField) and field.name == "id")
        ]
    )
    meta = INDENT + NEWLINE.join(
        filter(
            None,
            [
                "class Meta:",
                INDENT + 'table_name = "%s"' % Model._meta.table_name,
                (INDENT + 'schema = "%s"' % Model._meta.schema)
                if Model._meta.schema
                else "",
                (
                    INDENT
                    + "primary_key = pw.CompositeKey{0}".format(
                        Model._meta.primary_key.field_names
                    )
                )
                if isinstance(Model._meta.primary_key, pw.CompositeKey)
                else "",
                (INDENT + "indexes = %s" % Model._meta.indexes)
                if Model._meta.indexes
                else "",
            ],
        )
    )

    return template.format(classname=Model.__name__, fields=fields, meta=meta)


def create_model(Model: pw.Model, **kwargs) -> str:
    """Generate migrations to create model."""
    return "@migrator.create_model\n" + model_to_code(Model, **kwargs)


def remove_model(Model: pw.Model, **kwargs) -> str:
    """Generate migrations to remove model."""
    return "migrator.remove_model('%s')" % Model._meta.table_name


def create_fields(Model: pw.Model, *fields: pw.Field, **kwargs) -> str:
    """Generate migrations to add fields."""
    return "migrator.add_fields(%s'%s', %s)" % (
        NEWLINE,
        Model._meta.table_name,
        NEWLINE
        + ("," + NEWLINE).join(
            [field_to_code(field, False, **kwargs) for field in fields]
        ),
    )


def drop_fields(Model: pw.Model, *fields: pw.Field, **kwargs) -> str:
    """Generate migrations to remove fields."""
    return "migrator.remove_fields('%s', %s)" % (
        Model._meta.table_name,
        ", ".join(map(repr, fields)),
    )


def field_to_code(field: pw.Field, space: bool = True, **kwargs) -> str:
    """Generate field description."""
    col = Column(field, **kwargs)
    return col.get_field(" " if space else "")


def compare_fields(field1: pw.Field, field2: pw.Field, **kwargs) -> Dict:
    """Find diffs between the given fields."""
    ftype1, ftype2 = find_field_type(field1), find_field_type(field2)
    if ftype1 != ftype2:  # noqa
        return {"cls": True}

    params1 = field_to_params(field1)
    params1["null"] = field1.null
    params2 = field_to_params(field2)
    params2["null"] = field2.null

    return dict(set(params1.items()) - set(params2.items()))


def field_to_params(field: pw.Field, **kwargs) -> Dict:
    """Generate params for the given field."""
    ftype = find_field_type(field)
    params = FIELD_TO_PARAMS.get(ftype, lambda f: {})(field)
    if (
        field.default is not None
        and not callable(field.default)
        and isinstance(field.default, Hashable)
    ):
        params["default"] = field.default

    params["index"] = field.index and not field.unique, field.unique

    params.pop("backref", None)  # Ignore backref
    return params


def change_fields(Model: pw.Model, *fields: pw.Field, **kwargs) -> str:
    """Generate migrations to change fields."""
    return "migrator.change_fields('%s', %s)" % (
        Model._meta.table_name,
        ("," + NEWLINE).join([field_to_code(f, False) for f in fields]),
    )


def change_not_null(Model: pw.Model, name: str, null: bool) -> str:
    """Generate migrations."""
    operation = "drop_not_null" if null else "add_not_null"
    return "migrator.%s('%s', %s)" % (operation, Model._meta.table_name, repr(name))


def add_index(Model: pw.Model, name: Union[str, Iterable[str]], unique: bool) -> str:
    """Generate migrations."""
    columns = repr(name).strip("()[]")
    return f"migrator.add_index('{Model._meta.table_name}', {columns}, unique={unique})"


def drop_index(Model: pw.Model, name: Union[str, Iterable[str]]) -> str:
    """Generate migrations."""
    columns = repr(name).strip("()[]")
    return f"migrator.drop_index('{Model._meta.table_name}', {columns})"


def find_field_type(field: pw.Field) -> Type[pw.Field]:
    ftype = type(field)
    if ftype.__module__ not in PW_MODULES:
        for cls in ftype.mro():
            if cls.__module__ in PW_MODULES:
                return cls

    return ftype
