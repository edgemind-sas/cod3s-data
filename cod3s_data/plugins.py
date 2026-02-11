"""Plugin loading system for COD3S Data Framework."""

import importlib

from cod3s_data.config.factory import ComponentFactory


class PluginError(Exception):
    """Error raised when a plugin fails to load or register."""


def load_plugin(module_path: str, factory: ComponentFactory) -> None:
    """Load a single plugin module and call its register function.

    A plugin module must export a ``register(factory)`` function.
    As a fallback, ``register_all(factory)`` is also accepted for
    backwards compatibility with existing Gemini3D plugins.

    Args:
        module_path: Dotted Python module path (e.g. ``my_package.my_plugin``)
        factory: ComponentFactory to register components into

    Raises:
        PluginError: If the module cannot be imported, has no register
            function, or the register function raises an error
    """
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise PluginError(f"Cannot import plugin '{module_path}': {exc}") from exc

    register_fn = getattr(module, "register", None)
    if register_fn is None:
        register_fn = getattr(module, "register_all", None)

    if register_fn is None:
        raise PluginError(
            f"Plugin '{module_path}' has no 'register' or 'register_all' function"
        )

    if not callable(register_fn):
        raise PluginError(
            f"Plugin '{module_path}': 'register' is not callable"
        )

    try:
        register_fn(factory)
    except Exception as exc:
        raise PluginError(
            f"Plugin '{module_path}' register() failed: {exc}"
        ) from exc


def load_plugins(
    module_paths: list[str],
    factory: ComponentFactory,
    *,
    raise_on_error: bool = True,
) -> list[str]:
    """Load multiple plugin modules in order.

    Args:
        module_paths: List of dotted module paths to load
        factory: ComponentFactory to register components into
        raise_on_error: If True, raise on first error. If False,
            skip failed plugins and continue.

    Returns:
        List of successfully loaded plugin module paths

    Raises:
        PluginError: If raise_on_error is True and a plugin fails
    """
    loaded: list[str] = []
    for path in module_paths:
        try:
            load_plugin(path, factory)
            loaded.append(path)
        except PluginError:
            if raise_on_error:
                raise
    return loaded
