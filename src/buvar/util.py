import functools
import importlib
import inspect
import sys
import types
import typing as t


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


class cached:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        functools.update_wrapper(self, wrapped)

    def __get__(self, inst, cls=None):
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


def resolve_dotted_name(
    name: str, *, caller: t.Union[types.FrameType, int] = 0
) -> t.Union[types.ModuleType, t.Callable]:
    """Use pkg_resources style dotted name to resolve a name."""
    # skip resolving for module and coroutine
    if inspect.ismodule(name) or inspect.isroutine(name) or not isinstance(name, str):
        return name

    # relative import
    if name.startswith("."):
        # find coller package
        frame = (
            caller if isinstance(caller, types.FrameType) else sys._getframe(1 + caller)
        )
        caller_package = frame.f_globals["__package__"]
    else:
        caller_package = None

    part = ":"
    module_name, _, attr_name = name.partition(part)

    if part in attr_name:
        raise ValueError(f"Invalid name: {name}", name)

    try:
        resolved = importlib.import_module(module_name, caller_package)
    except ValueError as ex:
        raise ImportError(*ex.args)

    if attr_name:
        resolved = getattr(resolved, attr_name)

    return resolved


def fqdn(obj) -> str:
    return f"{obj.__module__}.{obj.__qualname__}"
