"""Unit tests for CLI module."""

import argparse
import types
from unittest.mock import MagicMock, patch

import pytest

from cod3s_data.cli import main, run_pipeline, validate_pipeline


class TestMainEntryPoint:
    def test_no_args_shows_help_and_returns_1(self, capsys):
        """main() with no args prints help and returns 1."""
        with patch("sys.argv", ["cod3s-data"]):
            result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower() or "COD3S Data Framework" in captured.out

    def test_version_flag(self):
        """--version exits with SystemExit(0)."""
        with patch("sys.argv", ["cod3s-data", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_unknown_command(self, capsys):
        """Unknown subcommand causes SystemExit(2) from argparse."""
        with patch("sys.argv", ["cod3s-data", "nonexistent"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2


class TestValidateCommand:
    def test_validate_valid_config(self, tmp_path, capsys):
        """validate on a valid YAML returns 0 and prints summary."""
        config_file = tmp_path / "valid.yaml"
        config_file.write_text(
            "name: test_pipeline\n"
            "sources:\n"
            "  - type: sequence\n"
            "    channel: numbers\n"
            "    params:\n"
            "      start_value: 1\n"
            "      end_value: 5\n"
            "      rate: 10.0\n"
            "destinations:\n"
            "  - type: console\n"
            "    channel_pattern: numbers\n"
            "    params: {}\n"
        )
        args = argparse.Namespace(config=str(config_file), verbose=False, plugin=None)
        result = validate_pipeline(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "Configuration is valid" in captured.out
        assert "test_pipeline" in captured.out
        assert "Sources: 1" in captured.out
        assert "Destinations: 1" in captured.out

    def test_validate_missing_file(self, capsys):
        """validate on non-existent file returns 1."""
        args = argparse.Namespace(config="/nonexistent/path.yaml", verbose=False, plugin=None)
        result = validate_pipeline(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_validate_invalid_yaml(self, tmp_path, capsys):
        """validate on invalid YAML returns 1."""
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text("sources:\n  - type: sequence\n    # missing channel\n")
        args = argparse.Namespace(config=str(config_file), verbose=False, plugin=None)
        result = validate_pipeline(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "invalid" in captured.err.lower()

    def test_validate_empty_yaml(self, tmp_path, capsys):
        """validate on empty YAML returns 1."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")
        args = argparse.Namespace(config=str(config_file), verbose=False, plugin=None)
        result = validate_pipeline(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "invalid" in captured.err.lower() or "Error" in captured.err

    def test_validate_verbose_shows_traceback(self, tmp_path, capsys):
        """validate --verbose shows traceback on error."""
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text("sources:\n  - type: sequence\n")
        args = argparse.Namespace(config=str(config_file), verbose=True, plugin=None)
        result = validate_pipeline(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "Traceback" in captured.err

    def test_validate_with_transformations(self, tmp_path, capsys):
        """validate prints transformations summary."""
        config_file = tmp_path / "transforms.yaml"
        config_file.write_text(
            "name: transform_pipeline\n"
            "sources:\n"
            "  - type: sequence\n"
            "    channel: input\n"
            "    params:\n"
            "      start_value: 0\n"
            "      end_value: 10\n"
            "      rate: 10.0\n"
            "transformations:\n"
            "  - type: map\n"
            "    input_channels: input\n"
            "    output_channel: output\n"
            "    params:\n"
            "      map_fn_code: \"lambda x: x * 2\"\n"
            "destinations:\n"
            "  - type: console\n"
            "    channel_pattern: output\n"
            "    params: {}\n"
        )
        args = argparse.Namespace(config=str(config_file), verbose=False, plugin=None)
        result = validate_pipeline(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "Transformations: 1" in captured.out

    def test_validate_with_yaml_plugin(self, tmp_path, capsys):
        """validate with plugin in YAML shows Plugins count."""
        config_file = tmp_path / "with_plugin.yaml"
        config_file.write_text(
            "name: plugin_test\n"
            "plugins:\n"
            "  - my.fake.plugin\n"
            "sources:\n"
            "  - type: sequence\n"
            "    channel: ch\n"
            "    params:\n"
            "      start_value: 0\n"
            "      end_value: 1\n"
            "      rate: 10.0\n"
            "destinations: []\n"
        )
        # Mock load_plugins to avoid real import
        with patch("cod3s_data.plugins.load_plugin"):
            args = argparse.Namespace(config=str(config_file), verbose=False, plugin=None)
            result = validate_pipeline(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Plugins: 1" in captured.out

    def test_validate_with_invalid_plugin(self, tmp_path, capsys):
        """validate with invalid plugin module returns error."""
        config_file = tmp_path / "bad_plugin.yaml"
        config_file.write_text(
            "name: bad_plugin_test\n"
            "plugins:\n"
            "  - nonexistent.module.xyz\n"
            "sources: []\n"
            "destinations: []\n"
        )
        args = argparse.Namespace(config=str(config_file), verbose=False, plugin=None)
        result = validate_pipeline(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "invalid" in captured.err.lower() or "Error" in captured.err


class TestRunCommand:
    def test_run_missing_file(self, capsys):
        """run on non-existent file returns 1."""
        args = argparse.Namespace(
            config="/nonexistent/path.yaml", verbose=False,
            log_level="INFO", json_logs=False, plugin=None,
        )
        result = run_pipeline(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_run_valid_batch_pipeline(self, tmp_path, capsys):
        """run with a fast batch pipeline completes and returns 0."""
        config_file = tmp_path / "batch.yaml"
        config_file.write_text(
            "name: batch_test\n"
            "broker:\n"
            "  enable_metrics: false\n"
            "sources:\n"
            "  - type: sequence\n"
            "    channel: data\n"
            "    params:\n"
            "      start_value: 0\n"
            "      end_value: 3\n"
            "      rate: 10000.0\n"
            "destinations:\n"
            "  - type: inmemory\n"
            "    channel_pattern: data\n"
            "    params: {}\n"
        )
        args = argparse.Namespace(
            config=str(config_file), verbose=False,
            log_level="WARNING", json_logs=False, plugin=None,
        )
        result = run_pipeline(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "completed successfully" in captured.out

    def test_run_verbose_on_error(self, tmp_path, capsys):
        """run --verbose shows traceback on error."""
        config_file = tmp_path / "bad.yaml"
        config_file.write_text("sources:\n  - type: unknown_type\n    channel: x\n")
        args = argparse.Namespace(
            config=str(config_file), verbose=True,
            log_level="WARNING", json_logs=False, plugin=None,
        )
        result = run_pipeline(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "Traceback" in captured.err

    def test_run_without_verbose_hides_traceback(self, tmp_path, capsys):
        """run without --verbose hides traceback on error."""
        config_file = tmp_path / "bad.yaml"
        config_file.write_text("sources:\n  - type: unknown_type\n    channel: x\n")
        args = argparse.Namespace(
            config=str(config_file), verbose=False,
            log_level="WARNING", json_logs=False, plugin=None,
        )
        result = run_pipeline(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "Traceback" not in captured.err
        assert "Error" in captured.err

    def test_run_json_logs_flag(self, tmp_path, capsys):
        """run --json-logs configures JSON logging without crashing."""
        config_file = tmp_path / "batch.yaml"
        config_file.write_text(
            "name: json_logs_test\n"
            "broker:\n"
            "  enable_metrics: false\n"
            "sources:\n"
            "  - type: sequence\n"
            "    channel: data\n"
            "    params:\n"
            "      start_value: 0\n"
            "      end_value: 2\n"
            "      rate: 10000.0\n"
            "destinations:\n"
            "  - type: inmemory\n"
            "    channel_pattern: data\n"
            "    params: {}\n"
        )
        args = argparse.Namespace(
            config=str(config_file), verbose=False,
            log_level="WARNING", json_logs=True, plugin=None,
        )
        result = run_pipeline(args)
        assert result == 0

    def test_run_log_level_debug(self, tmp_path, capsys):
        """run --log-level DEBUG does not crash."""
        config_file = tmp_path / "batch.yaml"
        config_file.write_text(
            "name: debug_test\n"
            "broker:\n"
            "  enable_metrics: false\n"
            "sources:\n"
            "  - type: sequence\n"
            "    channel: data\n"
            "    params:\n"
            "      start_value: 0\n"
            "      end_value: 2\n"
            "      rate: 10000.0\n"
            "destinations:\n"
            "  - type: inmemory\n"
            "    channel_pattern: data\n"
            "    params: {}\n"
        )
        args = argparse.Namespace(
            config=str(config_file), verbose=False,
            log_level="DEBUG", json_logs=False, plugin=None,
        )
        result = run_pipeline(args)
        assert result == 0

    def test_run_with_cli_plugin(self, tmp_path, capsys):
        """run --plugin loads the plugin before starting the pipeline."""
        config_file = tmp_path / "batch.yaml"
        config_file.write_text(
            "name: plugin_run_test\n"
            "broker:\n"
            "  enable_metrics: false\n"
            "sources:\n"
            "  - type: sequence\n"
            "    channel: data\n"
            "    params:\n"
            "      start_value: 0\n"
            "      end_value: 2\n"
            "      rate: 10000.0\n"
            "destinations:\n"
            "  - type: inmemory\n"
            "    channel_pattern: data\n"
            "    params: {}\n"
        )
        # Create a fake plugin module
        fake_plugin = types.ModuleType("fake_run_plugin")
        fake_plugin.register = MagicMock()

        with patch.dict("sys.modules", {"fake_run_plugin": fake_plugin}):
            args = argparse.Namespace(
                config=str(config_file), verbose=False,
                log_level="WARNING", json_logs=False,
                plugin=["fake_run_plugin"],
            )
            result = run_pipeline(args)

        assert result == 0
        fake_plugin.register.assert_called_once()


class TestMainIntegration:
    """Test main() dispatches correctly to subcommands."""

    def test_main_validate_dispatches(self, tmp_path, capsys):
        """main validate <file> dispatches to validate_pipeline."""
        config_file = tmp_path / "valid.yaml"
        config_file.write_text(
            "name: test\n"
            "sources:\n"
            "  - type: sequence\n"
            "    channel: ch\n"
            "    params:\n"
            "      start_value: 0\n"
            "      end_value: 1\n"
            "      rate: 10.0\n"
            "destinations: []\n"
        )
        with patch("sys.argv", ["cod3s-data", "validate", str(config_file)]):
            result = main()
        assert result == 0

    def test_main_run_dispatches(self, tmp_path, capsys):
        """main run <file> dispatches to run_pipeline."""
        config_file = tmp_path / "batch.yaml"
        config_file.write_text(
            "name: main_run_test\n"
            "broker:\n"
            "  enable_metrics: false\n"
            "sources:\n"
            "  - type: sequence\n"
            "    channel: data\n"
            "    params:\n"
            "      start_value: 0\n"
            "      end_value: 2\n"
            "      rate: 10000.0\n"
            "destinations:\n"
            "  - type: inmemory\n"
            "    channel_pattern: data\n"
            "    params: {}\n"
        )
        with patch("sys.argv", ["cod3s-data", "run", "--log-level", "WARNING", str(config_file)]):
            result = main()
        assert result == 0

    def test_main_validate_missing_file(self, capsys):
        """main validate with missing file returns 1."""
        with patch("sys.argv", ["cod3s-data", "validate", "/no/such/file.yaml"]):
            result = main()
        assert result == 1
