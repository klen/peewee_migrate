from playhouse.reflection import Column as VanilaColumn
from peewee import PrimaryKeyField

INDENT = '    '
NEWLINE = '\n' + INDENT


class Column(VanilaColumn):

    def __init__(self, *args, **kwargs):
        self.default = kwargs.pop('default', None)
        super(Column, self).__init__(*args, **kwargs)

    def get_field_parameters(self):
        params = super(Column, self).get_field_parameters()
        if self.default is not None and not callable(self.default):
            params['default'] = self.default
        return params

    def get_field(self, space=' '):
        # Generate the field definition for this column.
        field_params = self.get_field_parameters()
        param_str = ', '.join('%s=%s' % (k, repr(v))
                              for k, v in sorted(field_params.items()))
        return '{name}{space}={space}pw.{classname}({params})'.format(
            name=self.name, space=space, classname=self.field_class.__name__, params=param_str)


def diff_one(model1, model2):
    """Find difference between Peewee models."""
    changes = []

    fields1 = model1._meta.fields
    fields2 = model2._meta.fields

    # Add fields
    names = set(fields1) - set(fields2)
    if names:
        fields = [fields1[name] for name in names]
        changes.append(create_fields(model1, *fields))

    names = set(fields2) - set(fields1)
    if names:
        changes.append(drop_fields(model1, *names))

    #  for name, field1 in fields1.items():
        #  if name not in fields2:
        #  continue
        #  field2 = fields2[name]

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
        if not (isinstance(field, PrimaryKeyField) and field.name == 'id')
    ])
    return template.format(
        classname=Model.__name__,
        fields=fields
    )


def create_model(Model):
    return '@migrator.create_model\n' + model_to_code(Model)


def remove_model(Model):
    return 'migrator.remove_model("%s")' % Model._meta.name


def create_fields(Model, *fields):
    return 'migrator.add_fields(%s"%s", %s)' % (
        NEWLINE,
        Model._meta.name,
        NEWLINE + NEWLINE.join([field_to_code(field, False) for field in fields])
    )


def drop_fields(Model, *fields):
    return 'migrator.remove_fields("%s", %s)' % (
        Model._meta.name, ' '.join(fields)
    )


def field_to_code(field, space=True):
    col = Column(
        field.name,
        type(field),
        field.db_field,
        field.null,
        field.primary_key,
        field.db_column,
        field.index,
        field.unique,
        default=field.default
    )

    return col.get_field(' ' if space else '')
