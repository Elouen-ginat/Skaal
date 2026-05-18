from __future__ import annotations

import json
from typing import Any, cast


def decode_json_value(raw: Any) -> Any:
    if isinstance(raw, (str, bytes, bytearray)):
        return json.loads(raw)
    return raw


def serialize_value(value: Any, value_type: object) -> Any:
    if value_type is None:
        return value
    try:
        from pydantic import BaseModel

        if isinstance(value_type, type) and issubclass(value_type, BaseModel):
            if isinstance(value, BaseModel):
                return value.model_dump()
            if isinstance(value, dict):
                payload = cast(dict[str, Any], value)
                return value_type.model_validate(payload).model_dump()
    except ImportError:
        pass
    return cast(Any, value)


def deserialize_value(raw: Any, value_type: object) -> Any:
    if raw is None or value_type is None:
        return raw
    try:
        from pydantic import BaseModel

        if isinstance(value_type, type) and issubclass(value_type, BaseModel):
            if isinstance(raw, value_type):
                return raw
            decoded = decode_json_value(raw)
            if isinstance(decoded, dict):
                payload = cast(dict[str, Any], decoded)
                from skaal.types.schema import apply_migrations

                return value_type.model_validate(apply_migrations(payload, value_type))
    except ImportError:
        pass
    return raw
