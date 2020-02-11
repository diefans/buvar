import enum


class missing(enum.Enum):
    missing = 1


missing = missing.missing


class ResolveError(Exception):
    pass
