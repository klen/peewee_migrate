from warnings import warn


def depricated_method(fn, depricated_fn_name):
    def wrapper(*args, **kwargs):
        warn(
            f"{depricated_fn_name} is depricated. Use {fn.__name__} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return fn(*args, **kwargs)

    return wrapper
