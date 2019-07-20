# cython: language_level=3
cdef class Components:
    cdef dict namespaces
    cpdef list stack

    cdef _add(self, item, namespace=*, str name=*)
    cdef dict upstream(self, target=*, name=*)
    cdef dict _find(self, namespace)
    cdef _get(self, namespace, str name=*, default=*)
