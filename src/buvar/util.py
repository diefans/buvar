from functools import update_wrapper


class adict(dict):
    def __init__(self, *args, **kwargs):
        super(*args, **kwargs)
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
