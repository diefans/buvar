class ComponentLookupError(Exception):
    pass


try:
    # gains over 100% speed up
    from .c_components import Components as Components
except ImportError:
    from .py_components import Components as Components  # noqa: F40
