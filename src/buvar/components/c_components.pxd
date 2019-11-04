# cython: language_level=3
cdef class ComponentLookupError(Exception):
    pass

cdef class Components:
    cdef dict namespaces
    cpdef list stack

    cdef _push(self, namespaces, stack)
    cpdef pop(self)
    cdef _add(self, item, namespace=*, str name=*)
    cdef dict _find(self, namespace)
    cdef _get(self, namespace, name=*, default=*)
