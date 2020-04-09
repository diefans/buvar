import functools


def methdispatch(func):
    # https://stackoverflow.com/questions/24601722/how-can-i-use-functools-singledispatch-with-instance-methods
    dispatcher = functools.singledispatch(func)

    def wrapper(*args, **kw):
        return dispatcher.dispatch(args[1].__class__)(*args, **kw)

    wrapper.register = dispatcher.register
    functools.update_wrapper(wrapper, func)
    return wrapper


class adict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


class reify:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        functools.update_wrapper(self, wrapped)

    def __get__(self, inst, objtype=None):
        if inst is None:
            return self
        val = self.wrapped(inst)
        setattr(inst, self.wrapped.__name__, val)
        return val


def merge_dict(*sources, dest=None):
    """Merge `sources` into `dest`.

    `dest` is altered in place.
    """
    if dest is None:
        dest = {}
    for source in sources:
        for key, value in source.items():
            if isinstance(value, dict):
                # get node or create one
                node = dest.setdefault(key, {})
                merge_dict(value, dest=node)
            else:
                dest[key] = value
    return dest
