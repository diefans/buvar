try:
    # gains over 100% speed up
    from .c_components import Components
except ImportError:
    from .py_components import Components
