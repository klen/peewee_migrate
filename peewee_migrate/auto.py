from collections import OrderedDict
from collections.abc import Hashable

import peewee as pw
from playhouse.reflection import Column as VanilaColumn


INDENT = '    '
NEWLINE = '\n' + INDENT
FIELD_MODULES_MAP = {
    'ArrayField': 'pw_pext',
    'BinaryJSONField': 'pw_pext',
    'DateTimeTZField': 'pw_pext',
    'HStoreField': 'pw_pext',
    'IntervalField': 'pw_pext',
    'JSONField': 'pw_pext',
    'TSVectorField': 'pw_pext',
}


def fk_to_params(field: pw.ForeignKeyField):
    """Get params from the given fk."""
    params = {}
    if field.on_delete is not None:
        params['on_delete'] = "'%s'" % field.on_delete
    if field.on_update is not None:
        params['on_update'] = "'%s'" % field.on_update
    return params


def dtf_to_params(field: pw.DateTimeField):
    """Get params from the given datetime field."""
    params = {}
    if not isinstance(field.formats, list):
        params['formats'] = field.formats
    return params


FIELD_TO_PARAMS = {
    pw.CharField: lambda f: {'max_length': f.max_length},
    pw.DecimalField: lambda f: {
        'max_digits': f.max_digits, 'decimal_places': f.decimal_places,
        'auto_round': f.auto_round, 'rounding': f.rounding},
    pw.ForeignKeyField: fk_to_params,
    pw.DateTimeField: dtf_to_params,
}


class Column(VanilaColumn):

    def __init__(self, field, migrator=None):  # noqa
        super(Column, self).__init__(
            field.name, type(field), field.field_type, field.null,
            primary_key=field.primary_key, column_name=field.column_name, index=field.index,
            unique=field.unique, extra_parameters={}
        )
        if field.default is not None and not callable(field.default):
            self.default = repr(field.default)

        if self.field_class in FIELD_TO_PARAMS:
            self.extra_parameters.update(FIELD_TO_PARAMS[self.field_class](field))

        self.rel_model = None
        self.related_name = None
        self.to_field = None

        if isinstance(field, pw.ForeignKeyField):
            self.to_field = field.rel_field.name
            self.related_name = field.backref
            self.rel_model = "migrator.orm['%s']" % field.rel_model._meta.table_name

    def get_field(self, space=' '):
        # Generate the field definition for this column.
        field = super(Column, self).get_field()
        module = FIELD_MODULES_MAP.get(self.field_class.__name__, 'pw')
        name, _, field = [s and s.strip() for s in field.partition('=')]
        return '{name}{space}={space}{module}.{field}'.format(
            name=name, field=field, space=space, module=module)


def diff_one(model1, model2, **kwargs):
    """Find difference between given peewee models."""
    changes = []

    fields1 = model1._meta.fields
    fields2 = model2._meta.fields

    # Add fields
    names1 = set(fields1) - set(fields2)
    if names1:
        fields = [fields1[name] for name in names1]
        changes.append(create_fields(model1, *fields, **kwargs))

    # Drop fields
    names2 = set(fields2) - set(fields1)
    if names2:
        changes.append(drop_fields(model1, *names2))

    # Change fields
    fields_ = []
    nulls_ = []
    indexes_ = []
    for name in set(fields1) - names1 - names2:
        field1, field2 = fields1[name], fields2[name]
        diff = compare_fields(field1, field2)
        null = diff.pop('null', None)
        index = diff.pop('index', None)

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
            if fields2[name].unique or fields2[name].index:
                changes.append(drop_index(model1, name))
            changes.append(add_index(model1, name, unique))
        else:
            changes.append(drop_index(model1, name))

    return changes


def diff_many(models1, models2, migrator=None, reverse=False):
    """Calculate changes for migrations from models2 to models1."""
    models1 = pw.sort_models(models1)
    models2 = pw.sort_models(models2)

    if reverse:
        models1 = reversed(models1)
        models2 = reversed(models2)

    models1 = OrderedDict([(m._meta.name, m) for m in models1])
    models2 = OrderedDict([(m._meta.name, m) for m in models2])

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


def model_to_code(Model, **kwargs):
    template = """class {classname}(pw.Model):
{fields}

{meta}
"""
    fields = INDENT + NEWLINE.join([
        field_to_code(field, **kwargs) for field in Model._meta.sorted_fields
        if not (isinstance(field, pw.PrimaryKeyField) and field.name == 'id')
    ])
    meta = INDENT + NEWLINE.join(filter(None, [
        'class Meta:',
        INDENT + 'table_name = "%s"' % Model._meta.table_name,
        (INDENT + 'schema = "%s"' % Model._meta.schema) if Model._meta.schema else '',
        (INDENT + 'primary_key = pw.CompositeKey{0}'.format(Model._meta.primary_key.field_names))
        if isinstance(Model._meta.primary_key, pw.CompositeKey) else '',
        (INDENT + 'indexes = %s' % Model._meta.indexes) if Model._meta.indexes else '',
    ]))

    return template.format(classname=Model.__name__, fields=fields, meta=meta)


def create_model(Model, **kwargs):
    return '@migrator.create_model\n' + model_to_code(Model, **kwargs)


def remove_model(Model, **kwargs):
    return "migrator.remove_model('%s')" % Model._meta.table_name


def create_fields(Model, *fields, **kwargs):
    return "migrator.add_fields(%s'%s', %s)" % (
        NEWLINE,
        Model._meta.table_name,
        NEWLINE + (',' + NEWLINE).join([field_to_code(field, False, **kwargs) for field in fields])
    )


def drop_fields(Model, *fields, **kwargs):
    return "migrator.remove_fields('%s', %s)" % (
        Model._meta.table_name, ', '.join(map(repr, fields))
    )


def field_to_code(field, space=True, **kwargs):
    col = Column(field, **kwargs)
    return col.get_field(' ' if space else '')


def compare_fields(field1, field2, **kwargs):
    field_cls1, field_cls2 = type(field1), type(field2)
    if field_cls1 != field_cls2:  # noqa
        return {'cls': True}

    params1 = field_to_params(field1)
    params1['null'] = field1.null
    params2 = field_to_params(field2)
    params2['null'] = field2.null

    return dict(set(params1.items()) - set(params2.items()))


def field_to_params(field, **kwargs):
    params = FIELD_TO_PARAMS.get(type(field), lambda f: {})(field)
    if field.default is not None and \
            not callable(field.default) and isinstance(field.default, Hashable):
        params['default'] = field.default

    params['index'] = field.index and not field.unique, field.unique

    params.pop('backref', None)  # Ignore backref
    return params


def change_fields(Model, *fields, **kwargs):
    return "migrator.change_fields('%s', %s)" % (
        Model._meta.table_name, (',' + NEWLINE).join([field_to_code(f, False) for f in fields])
    )


def change_not_null(Model, name, null):
    operation = 'drop_not_null' if null else 'add_not_null'
    return "migrator.%s('%s', %s)" % (operation, Model._meta.table_name, repr(name))


def add_index(Model, name, unique):
    operation = 'add_index'
    return "migrator.%s('%s', %s, unique=%s)" %\
        (operation, Model._meta.table_name, repr(name), unique)


def drop_index(Model, name):
    operation = 'drop_index'
    return "migrator.%s('%s', %s)" % (operation, Model._meta.table_name, repr(name))
