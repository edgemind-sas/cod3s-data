"""Every public method of the package carries a docstring of its own.

This is the surface someone reads when writing a custom component or a test:
the base classes and the test helpers. It was undocumented in 27 places before
this check existed, so the check is what keeps it documented.

`__doc__` is deliberate, rather than `inspect.getdoc`: the latter falls back to
the base class's text, which would let an override that documents nothing pass
by borrowing a description of what the *base* does.

Properties are not covered — the audit behind this check counted methods, and
sixteen public properties are still undocumented.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import cod3s_data


def _undocumented_public_methods() -> list[str]:
    found: set[str] = set()

    for module_info in pkgutil.walk_packages(cod3s_data.__path__, "cod3s_data."):
        try:
            module = importlib.import_module(module_info.name)
        except ImportError:
            continue  # optional extra not installed (influxdb, observatory)

        for class_name, cls in inspect.getmembers(module, inspect.isclass):
            # Only classes defined here, not ones imported into the namespace.
            if cls.__module__ != module_info.name or class_name.startswith("_"):
                continue

            for method_name, method in inspect.getmembers(cls, inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                # Skip inherited methods; they belong to the class that defines them.
                if method.__qualname__.split(".")[0] != class_name:
                    continue
                if not (method.__doc__ or "").strip():
                    found.add(f"{module_info.name}:{class_name}.{method_name}")

    return sorted(found)


def test_public_methods_have_docstrings() -> None:
    undocumented = _undocumented_public_methods()
    assert not undocumented, "Public methods without a docstring:\n  " + "\n  ".join(undocumented)
