from functools import update_wrapper


class adict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


class reify:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        update_wrapper(self, wrapped)

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
