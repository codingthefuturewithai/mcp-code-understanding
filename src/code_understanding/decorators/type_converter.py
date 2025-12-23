"""Type Converter Decorator for MCP Tools - Handles Runtime Type Conversion.

This decorator handles runtime type conversion for MCP tools when clients send
incorrect types (e.g., strings instead of integers). This is particularly important
for certain MCP clients that may send all parameters as strings.
"""

import asyncio
import inspect
import json
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Union, get_args, get_origin


def type_converter(func: Callable) -> Callable:
    """Convert string parameters to their proper types based on function annotations.

    This decorator performs runtime type conversion for MCP tools. Many MCP clients
    send all parameters as strings, requiring server-side conversion to the proper types.

    Supported conversions:
    - str -> int
    - str -> float
    - str -> bool (handles "true"/"false", "True"/"False", "1"/"0")
    - str -> List (parses JSON strings)
    - str -> Dict (parses JSON strings)
    - Handles Optional types by checking for None first
    """
    sig = inspect.signature(func)

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        """Async wrapper that performs type conversion."""
        converted_kwargs = {}

        for param_name, param in sig.parameters.items():
            if param_name not in kwargs:
                if param.default != inspect.Parameter.empty:
                    converted_kwargs[param_name] = param.default
                continue

            value = kwargs[param_name]

            if value is None:
                converted_kwargs[param_name] = None
                continue

            annotation = param.annotation
            if annotation == inspect.Parameter.empty:
                converted_kwargs[param_name] = value
                continue

            # Handle Optional types
            origin = get_origin(annotation)
            if origin is Union:
                args_types = get_args(annotation)
                non_none_types = [t for t in args_types if t != type(None)]
                if non_none_types:
                    annotation = non_none_types[0]
                    origin = get_origin(annotation)

            # Perform type conversion
            try:
                converted_value = _convert_value(value, annotation, origin)
                converted_kwargs[param_name] = converted_value
            except (ValueError, TypeError, json.JSONDecodeError):
                converted_kwargs[param_name] = value

        return await func(**converted_kwargs)

    async_wrapper.__signature__ = sig
    async_wrapper.__annotations__ = func.__annotations__
    return async_wrapper


def _convert_value(value: Any, target_type: type, origin: Optional[type]) -> Any:
    """Convert a single value to the target type."""
    if isinstance(value, target_type) and origin is None:
        return value

    if isinstance(value, str):
        if target_type == int:
            return int(value)
        elif target_type == float:
            return float(value)
        elif target_type == bool:
            return _str_to_bool(value)
        elif origin is list or target_type == list:
            if value.startswith("[") and value.endswith("]"):
                return json.loads(value)
            else:
                return [value]
        elif origin is dict or target_type == dict:
            if value.startswith("{") and value.endswith("}"):
                return json.loads(value)
            else:
                raise ValueError(f"Cannot convert '{value}' to dict")

    elif isinstance(value, list) and (origin is list or target_type == list):
        element_types = get_args(target_type)
        if element_types:
            element_type = element_types[0]
            return [
                (
                    _convert_value(item, element_type, get_origin(element_type))
                    if not isinstance(item, element_type)
                    else item
                )
                for item in value
            ]
        return value

    return value


def _str_to_bool(value: str) -> bool:
    """Convert string to boolean."""
    if value.lower() in ("true", "1", "yes", "on"):
        return True
    elif value.lower() in ("false", "0", "no", "off"):
        return False
    else:
        raise ValueError(f"Cannot convert '{value}' to bool")
