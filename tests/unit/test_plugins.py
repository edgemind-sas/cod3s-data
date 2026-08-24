"""Unit tests for plugin loading system."""

import types
from unittest.mock import MagicMock, patch

import pytest

from cod3s_data.plugins import PluginError, load_plugin, load_plugins


@pytest.fixture
def factory():
    """Create a mock ComponentFactory."""
    return MagicMock()


class TestLoadPlugin:
    def test_load_plugin_with_register(self, factory):
        """Plugin with register() is loaded correctly."""
        module = types.ModuleType("fake_plugin")
        module.register = MagicMock()

        with patch("cod3s_data.plugins.importlib.import_module", return_value=module):
            load_plugin("fake_plugin", factory)

        module.register.assert_called_once_with(factory)

    def test_load_plugin_with_register_all_fallback(self, factory):
        """Plugin with only register_all() uses it as fallback."""
        module = types.ModuleType("fake_plugin")
        module.register_all = MagicMock()

        with patch("cod3s_data.plugins.importlib.import_module", return_value=module):
            load_plugin("fake_plugin", factory)

        module.register_all.assert_called_once_with(factory)

    def test_register_takes_priority_over_register_all(self, factory):
        """When both register and register_all exist, register is preferred."""
        module = types.ModuleType("fake_plugin")
        module.register = MagicMock()
        module.register_all = MagicMock()

        with patch("cod3s_data.plugins.importlib.import_module", return_value=module):
            load_plugin("fake_plugin", factory)

        module.register.assert_called_once_with(factory)
        module.register_all.assert_not_called()

    def test_nonexistent_module_raises_plugin_error(self, factory):
        """Importing a nonexistent module raises PluginError."""
        with pytest.raises(PluginError, match="Cannot import plugin"):
            load_plugin("nonexistent.module.xyz", factory)

    def test_module_without_register_raises_plugin_error(self, factory):
        """Module without register or register_all raises PluginError."""
        module = types.ModuleType("empty_plugin")

        with patch("cod3s_data.plugins.importlib.import_module", return_value=module), pytest.raises(PluginError, match="no 'register' or 'register_all'"):
            load_plugin("empty_plugin", factory)

    def test_non_callable_register_raises_plugin_error(self, factory):
        """Module with non-callable register attribute raises PluginError."""
        module = types.ModuleType("bad_plugin")
        module.register = "not a function"

        with patch("cod3s_data.plugins.importlib.import_module", return_value=module), pytest.raises(PluginError, match="not callable"):
            load_plugin("bad_plugin", factory)

    def test_register_that_raises_wraps_in_plugin_error(self, factory):
        """If register() raises, the error is wrapped in PluginError."""
        module = types.ModuleType("failing_plugin")
        module.register = MagicMock(side_effect=RuntimeError("boom"))

        with patch("cod3s_data.plugins.importlib.import_module", return_value=module), pytest.raises(PluginError, match="register\\(\\) failed: boom"):
            load_plugin("failing_plugin", factory)


class TestLoadPlugins:
    def test_load_multiple_plugins_in_order(self, factory):
        """Multiple plugins are loaded in declaration order."""
        call_order = []

        def make_module(name):
            mod = types.ModuleType(name)
            mod.register = lambda f: call_order.append(name)
            return mod

        def fake_import(path):
            return make_module(path)

        with patch("cod3s_data.plugins.importlib.import_module", side_effect=fake_import):
            loaded = load_plugins(["plugin_a", "plugin_b", "plugin_c"], factory)

        assert loaded == ["plugin_a", "plugin_b", "plugin_c"]
        assert call_order == ["plugin_a", "plugin_b", "plugin_c"]

    def test_raise_on_error_true_stops_at_first_failure(self, factory):
        """With raise_on_error=True, stops at first failing plugin."""
        module_a = types.ModuleType("plugin_a")
        module_a.register = MagicMock()

        def fake_import(path):
            if path == "plugin_a":
                return module_a
            raise ImportError("nope")

        with patch("cod3s_data.plugins.importlib.import_module", side_effect=fake_import), pytest.raises(PluginError):
            load_plugins(["plugin_a", "plugin_bad", "plugin_c"], factory)

    def test_raise_on_error_false_continues_on_failure(self, factory):
        """With raise_on_error=False, skips failed plugins and continues."""
        module_a = types.ModuleType("plugin_a")
        module_a.register = MagicMock()
        module_c = types.ModuleType("plugin_c")
        module_c.register = MagicMock()

        def fake_import(path):
            if path == "plugin_a":
                return module_a
            if path == "plugin_c":
                return module_c
            raise ImportError("nope")

        with patch("cod3s_data.plugins.importlib.import_module", side_effect=fake_import):
            loaded = load_plugins(
                ["plugin_a", "plugin_bad", "plugin_c"],
                factory,
                raise_on_error=False,
            )

        assert loaded == ["plugin_a", "plugin_c"]

    def test_empty_list_is_noop(self, factory):
        """Empty plugin list returns empty list without errors."""
        loaded = load_plugins([], factory)
        assert loaded == []
