_REFS = set()


def add_ref(value):
    if value in _REFS:
        raise ValueError('Duplicate reference %r' % value)
    _REFS.add(value)
