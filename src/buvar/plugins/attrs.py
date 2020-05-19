import functools

import attr
import cattr
import typing_inspect

import pendulum


class Converter(cattr.Converter):
    """This py:obj:`Converter` is relaxed in terms of ignoring undefined and
       defaulting to None on optional attributes.
    """

    def structure_attrs_fromdict(self, obj, cl):
        # type: (Mapping, Type) -> Any
        """Instantiate an attrs class from a mapping (dict)."""
        # For public use.
        # conv_obj = obj.copy()  # Dict of converted parameters.
        conv_obj = {}
        dispatch = self._structure_func.dispatch
        for a in attr.fields(cl):
            # We detect the type by metadata.
            type_ = a.type
            if type_ is None:
                # No type.
                continue
            name = a.name
            try:
                val = obj[name]
            except KeyError:
                if typing_inspect.is_optional_type(type_):
                    if a.default is attr.NOTHING:
                        val = None
                    else:
                        continue
                else:
                    continue

            conv_obj[name] = dispatch(type_)(val, type_)

        return cl(**conv_obj)


converter = Converter()

structure = converter.structure
unstructure = converter.unstructure


def _structure_pendulum(d, _=None):
    return d if isinstance(d, pendulum.DateTime) else pendulum.parse(d, tz="UTC")


pendulum_val = functools.partial(attr.ib, converter=_structure_pendulum)
converter.register_structure_hook(pendulum.DateTime, _structure_pendulum)
converter.register_unstructure_hook(pendulum.DateTime, str)
