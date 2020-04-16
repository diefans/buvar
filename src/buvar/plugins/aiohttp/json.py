import abc
import typing

import aiohttp.web
import attr

from buvar import context, util
import orjson

from . import attrs


class Jsonify(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def loads(self, str):
        ...

    @abc.abstractmethod
    def dumps(self, obj):
        ...

    def default(self, obj):
        if hasattr(obj, "__json__"):
            return obj.__json__()
        elif attr.has(obj):
            return attrs.unstructure(obj)
        else:
            return obj


class OrjsonJsonify(Jsonify):
    def loads(self, str):
        return orjson.loads(str)

    @util.methdispatch
    def default(self, obj):
        return super().default(obj)

    def dumps(self, obj):
        return orjson.dumps(obj, default=self.default)


def response(
    data: typing.Any,
    status: int = 200,
    reason: typing.Optional[str] = None,
    headers: aiohttp.web_response.LooseHeaders = None,
) -> aiohttp.web.Response:
    jsonify = context.get(Jsonify)
    body = jsonify.dumps(data)
    return aiohttp.web.Response(
        body=body,
        status=status,
        reason=reason,
        headers=headers,
        content_type="application/json",
    )


async def prepare():
    context.add(OrjsonJsonify())
