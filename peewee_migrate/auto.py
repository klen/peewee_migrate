from collections import Hashable, OrderedDict

import peewee as pw
from playhouse.reflection import Column as VanilaColumn


INDENT = '    '
NEWLINE = '\n' + INDENT


def fk_to_params(field):
    params = {}
    if field.on_delete is not None:
        params['on_delete'] = field.on_delete
    if field.on_update is not None:
        params['on_update'] = field.on_update
    return params


FIELD_TO_PARAMS = {
    pw.CharField: lambda f: {'max_length': f.max_length},
    pw.DecimalField: lambda f: {
        'max_digits': f.max_digits, 'decimal_places': f.decimal_places,
        'auto_round': f.auto_round, 'rounding': f.rounding},
    pw.ForeignKeyField: fk_to_params,
}


class Column(VanilaColumn):

    def __init__(self, field, migrator=None):  # noqa
        self.name = field.name
        self.field_class = type(field)
        self.nullable = field.null
        self.primary_key = field.primary_key
        self.db_column = field.db_column
        self.index = field.index
        self.unique = field.unique
        self.params = {}
        if field.default is not None and not callable(field.default):
            self.params['default'] = field.default

        if self.field_class in FIELD_TO_PARAMS:
            self.params.update(FIELD_TO_PARAMS[self.field_class](field))

        self.rel_model = None
        self.related_name = None
        self.to_field = None

        if isinstance(field, pw.ForeignKeyField):
            self.to_field = field.to_field.name
            if migrator and field.rel_model._meta.name in migrator.orm:
                self.rel_model = "migrator.orm['%s']" % field.rel_model._meta.name
            else:
                self.rel_model = field.rel_model.__name__

    def get_field_parameters(self):
        params = super(Column, self).get_field_parameters()
        params.update({k: repr(v) for k, v in self.params.items()})
        return params

    def get_field(self, space=' '):
        # Generate the field definition for this column.
        field_params = self.get_field_parameters()
        param_str = ', '.join('%s=%s' % (k, v)
                              for k, v in sorted(field_params.items()))
        return '{name}{space}={space}pw.{classname}({params})'.format(
            name=self.name, space=space, classname=self.field_class.__name__, params=param_str)


def diff_one(model1, model2, **kwargs):
    """Find difference between Peewee models."""
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
    for name in set(fields1) - names1 - names2:
        field1, field2 = fields1[name], fields2[name]
        diff = compare_fields(field1, field2)
        null = diff.pop('null', None)
        if diff:
            fields_.append(field1)

        if null is not None:
            nulls_.append((name, null))

    if fields_:
        changes.append(change_fields(model1, *fields_, **kwargs))

    for name, null in nulls_:
        changes.append(change_not_null(model1, name, null))

    return changes


def diff_many(models1, models2, migrator=None, reverse=False):
    models1 = pw.sort_models_topologically(models1)
    models2 = pw.sort_models_topologically(models2)

    if reverse:
        models1 = reversed(models1)
        models2 = reversed(models2)

    models1 = OrderedDict([(m._meta.name, m) for m in models1])
    models2 = OrderedDict([(m._meta.name, m) for m in models2])

    changes = []

    # Add models
    for name in [m for m in models1 if m not in models2]:
        changes.append(create_model(models1[name], migrator=migrator))

    # Remove models
    for name in [m for m in models2 if m not in models1]:
        changes.append(remove_model(models2[name]))

    for name, model1 in models1.items():
        if name not in models2:
            continue
        changes += diff_one(model1, models2[name], migrator=migrator)

    return changes


def model_to_code(Model, **kwargs):
    template = """class {classname}(pw.Model):
{fields}
"""
    fields = INDENT + NEWLINE.join([
        field_to_code(field, **kwargs) for field in Model._meta.sorted_fields
        if not (isinstance(field, pw.PrimaryKeyField) and field.name == 'id')
    ])
    return template.format(
        classname=Model.__name__,
        fields=fields
    )


def create_model(Model, **kwargs):
    return '@migrator.create_model\n' + model_to_code(Model, **kwargs)


def remove_model(Model, **kwargs):
    return "migrator.remove_model('%s')" % Model._meta.db_table


def create_fields(Model, *fields, **kwargs):
    return "migrator.add_fields(%s'%s', %s)" % (
        NEWLINE,
        Model._meta.db_table,
        NEWLINE + (',' + NEWLINE).join([field_to_code(field, False, **kwargs) for field in fields])
    )


def drop_fields(Model, *fields, **kwargs):
    return "migrator.remove_fields('%s', %s)" % (
        Model._meta.db_table, ', '.join(map(repr, fields))
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
            not callable(field.default) and \
            isinstance(field.default, Hashable):
        params['default'] = field.default
    return params


def change_fields(Model, *fields, **kwargs):
    return "migrator.change_fields('%s', %s)" % (
        Model._meta.db_table, (',' + NEWLINE).join([field_to_code(f, False) for f in fields])
    )


def change_not_null(Model, name, null):
    operation = 'drop_not_null' if null else 'add_not_null'
    return "migrator.%s('%s', %s)" % (operation, Model._meta.db_table, repr(name))
