# cython: language_level=3
cdef class Components:
    cdef dict namespaces
    cdef list _stack

    cdef _push(self, namespaces, stack)
    cpdef pop(self)
    cdef _add(self, item, namespace=*, name=*)
    cdef dict _find(self, namespace)
    cdef _get(self, namespace, name=*, default=*)
