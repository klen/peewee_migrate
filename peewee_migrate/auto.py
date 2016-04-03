from collections import Hashable

import peewee as pw
from playhouse.reflection import Column as VanilaColumn


INDENT = '    '
NEWLINE = '\n' + INDENT

FIELD_TO_PARAMS = {
    pw.CharField: lambda f: {'max_length': f.max_length},
    pw.DecimalField: lambda f: {
        'max_digits': f.max_digits, 'decimal_places': f.decimal_places,
        'auto_round': f.auto_round, 'rounding': f.rounding},
    # pw.ForeignKeyField: lambda f: {
    #     'rel_model': f.rel_model.__name__, 'related_name': f.related_name,
    #     'on_delete': f.on_delete, 'on_update': f.on_update , 'to_field': f.to_field.name
    # },
}


class Column(VanilaColumn):

    def __init__(self, field):
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
            self.rel_model = field.rel_model
            self.related_name = field.related_name

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


def diff_one(model1, model2):
    """Find difference between Peewee models."""
    changes = []

    fields1 = model1._meta.fields
    fields2 = model2._meta.fields

    # Add fields
    names1 = set(fields1) - set(fields2)
    if names1:
        fields = [fields1[name] for name in names1]
        changes.append(create_fields(model1, *fields))

    # Drop fields
    names2 = set(fields2) - set(fields1)
    if names2:
        changes.append(drop_fields(model1, *names2))

    # Change fields
    fields_ = []
    for name in set(fields1) - names1 - names2:
        field1, field2 = fields1[name], fields2[name]
        if compare_fields(field1, field2):
            fields_.append(field1)

    if fields_:
        changes.append(change_fields(model1, *fields_))

    return changes


def diff_many(models1, models2):
    models1 = {m._meta.name: m for m in models1}
    models2 = {m._meta.name: m for m in models2}

    changes = []

    # Add models
    for name in set(models1) - set(models2):
        changes.append(create_model(models1[name]))

    # Remove models
    for name in set(models2) - set(models1):
        changes.append(remove_model(models2[name]))

    for name, model1 in models1.items():
        if name not in models2:
            continue
        changes += diff_one(model1, models2[name])

    return changes


def model_to_code(Model):
    template = """class {classname}(pw.Model):
{fields}
"""
    fields = INDENT + NEWLINE.join([
        field_to_code(field) for field in Model._meta.sorted_fields
        if not (isinstance(field, pw.PrimaryKeyField) and field.name == 'id')
    ])
    return template.format(
        classname=Model.__name__,
        fields=fields
    )


def create_model(Model):
    return '@migrator.create_model\n' + model_to_code(Model)


def remove_model(Model):
    return "migrator.remove_model('%s')" % Model._meta.db_table


def create_fields(Model, *fields):
    return "migrator.add_fields(%s'%s', %s)" % (
        NEWLINE,
        Model._meta.db_table,
        NEWLINE + (',' + NEWLINE).join([field_to_code(field, False) for field in fields])
    )


def drop_fields(Model, *fields):
    return "migrator.remove_fields('%s', %s)" % (
        Model._meta.db_table, ', '.join(map(repr, fields))
    )


def field_to_code(field, space=True):
    col = Column(field)
    return col.get_field(' ' if space else '')


def compare_fields(field1, field2):
    field_cls1, field_cls2 = type(field1), type(field2)
    if field_cls1 != field_cls2:  # noqa
        return True

    params1 = field_to_params(field1)
    params2 = field_to_params(field2)

    return set(params1.items()) - set(params2.items())


def field_to_params(field):
    params = FIELD_TO_PARAMS.get(type(field), lambda f: {})(field)
    if field.default is not None and \
            not callable(field.default) and \
            isinstance(field.default, Hashable):
        params['default'] = field.default
    return params


def change_fields(Model, *fields):
    return "migrator.change_fields('%s', %s)" % (
        Model._meta.db_table, (',' + NEWLINE).join([field_to_code(f, False) for f in fields])
    )
