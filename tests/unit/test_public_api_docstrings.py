"""Every public method and property of the package carries its own docstring.

This is the surface someone reads when writing a custom component or a test:
the base classes and the test helpers. It was undocumented in 27 methods and 16
properties before these checks existed, so the checks are what keep it
documented.

`__doc__` is deliberate, rather than `inspect.getdoc`: the latter falls back to
the base class's text, which would let an override that documents nothing pass
by borrowing a description of what the *base* does. That holds for properties
too — `inspect.getdoc` on a mute redefined property returns its parent's text —
so they are read through `fget.__doc__`, the function actually being defined,
which is where the decorator puts the text and where nothing inherits.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Iterator

import cod3s_data


def _public_classes() -> Iterator[tuple[str, str, type]]:
    """Yield (module name, class name, class) for every public class of the package."""
    for module_info in pkgutil.walk_packages(cod3s_data.__path__, "cod3s_data."):
        try:
            module = importlib.import_module(module_info.name)
        except ImportError:
            continue  # optional extra not installed (influxdb, observatory)

        for class_name, cls in inspect.getmembers(module, inspect.isclass):
            # Only classes defined here, not ones imported into the namespace.
            if cls.__module__ != module_info.name or class_name.startswith("_"):
                continue
            yield module_info.name, class_name, cls


def _undocumented_public_methods() -> list[str]:
    found: set[str] = set()

    for module_name, class_name, cls in _public_classes():
        for method_name, method in inspect.getmembers(cls, inspect.isfunction):
            if method_name.startswith("_"):
                continue
            # Skip inherited methods; they belong to the class that defines them.
            if method.__qualname__.split(".")[0] != class_name:
                continue
            if not (method.__doc__ or "").strip():
                found.add(f"{module_name}:{class_name}.{method_name}")

    return sorted(found)


def _undocumented_public_properties() -> list[str]:
    found: set[str] = set()

    for module_name, class_name, cls in _public_classes():
        for prop_name, prop in inspect.getmembers(cls, lambda m: isinstance(m, property)):
            if prop_name.startswith("_"):
                continue
            # A property has no __qualname__ to test, so identity is the check:
            # anything not in the class's own __dict__ came from a base class.
            if prop_name not in vars(cls):
                continue
            # fget, not inspect.getdoc: the latter falls back to the base class.
            if prop.fget is None or not (prop.fget.__doc__ or "").strip():
                found.add(f"{module_name}:{class_name}.{prop_name}")

    return sorted(found)


def test_public_methods_have_docstrings() -> None:
    undocumented = _undocumented_public_methods()
    assert not undocumented, "Public methods without a docstring:\n  " + "\n  ".join(undocumented)


def test_public_properties_have_docstrings() -> None:
    undocumented = _undocumented_public_properties()
    assert not undocumented, "Public properties without a docstring:\n  " + "\n  ".join(
        undocumented
    )
