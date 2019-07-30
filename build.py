"""Build c_resolve cython extension."""


def build(setup_kwargs):
    """Needed for the poetry building interface."""

    try:
        from Cython.Build import cythonize
    except ImportError:
        pass
    else:
        # use cythonize to build the extensions
        modules = ["src/buvar/di/c_di.pyx", "src/buvar/components/c_components.pyx"]

        extensions = cythonize(modules)
        setup_kwargs.update({"ext_modules": extensions, "include_dirs": []})
