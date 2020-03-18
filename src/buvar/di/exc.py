missing = type.__new__(
    type, "missing", (object,), {"__repr__": lambda self: self.__class__.__name__}
)()


class ResolveError(Exception):
    pass
