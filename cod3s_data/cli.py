"""Command-line interface for COD3S Data Framework."""

import argparse
import asyncio
import sys
from pathlib import Path

from cod3s_data.config.loaders import load_yaml
from cod3s_data.framework import Framework
from cod3s_data.observability.logging import configure_logging


def run_pipeline(args: argparse.Namespace) -> int:
    """Run a pipeline from configuration file.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, 1 for error)
    """
    config_path = Path(args.config)

    # Check file exists
    if not config_path.exists():
        print(f"Error: Configuration file not found: {config_path}", file=sys.stderr)
        return 1

    # Configure logging
    log_level = args.log_level.upper()
    log_format = "json" if args.json_logs else "console"
    configure_logging(level=log_level, format=log_format)

    try:
        # Load configuration
        print(f"Loading configuration from {config_path}")
        config = load_yaml(config_path)

        # Merge CLI plugins into config
        cli_plugins = args.plugin or []
        for p in cli_plugins:
            if p not in config.plugins:
                config.plugins.append(p)

        # Resolve Observatory setting
        observatory_enabled = getattr(args, "observatory", False)
        observatory_port = getattr(args, "observatory_port", None)
        interactive = getattr(args, "interactive", False)

        # --interactive implies --observatory
        if interactive:
            observatory_enabled = True

        observatory: bool | object = observatory_enabled
        if observatory_enabled:
            try:
                from cod3s_data.observatory.config import ObservatoryConfig

                port = observatory_port or 8765
                observatory = ObservatoryConfig(port=port, interactive=interactive)
            except ImportError:
                print(
                    "Warning: Observatory dependencies not installed. "
                    "Install with: pip install cod3s-data[observatory]",
                    file=sys.stderr,
                )
                observatory = False

        # Run pipeline
        if interactive and observatory:
            port_val = observatory_port or 8765
            print(f"Starting pipeline: {config.name} (Interactive mode)")
            print(f"Pipeline ready, open http://127.0.0.1:{port_val} to start")
        elif observatory:
            print(f"Starting pipeline: {config.name} (Observatory enabled)")
        else:
            print(f"Starting pipeline: {config.name}")

        async def run():
            async with Framework(config, observatory=observatory) as framework:
                await framework.run()

        asyncio.run(run())

        print("\nPipeline completed successfully!")
        return 0

    except KeyboardInterrupt:
        print("\nPipeline interrupted by user", file=sys.stderr)
        return 130  # Standard exit code for SIGINT
    except Exception as e:
        print(f"Error running pipeline: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def validate_pipeline(args: argparse.Namespace) -> int:
    """Validate a pipeline configuration file.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, 1 for error)
    """
    config_path = Path(args.config)

    # Check file exists
    if not config_path.exists():
        print(f"Error: Configuration file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        # Load and validate configuration
        print(f"Validating configuration: {config_path}")
        config = load_yaml(config_path)

        # Merge CLI plugins into config
        cli_plugins = args.plugin or []
        for p in cli_plugins:
            if p not in config.plugins:
                config.plugins.append(p)

        # Load plugins to validate types
        all_plugins = config.plugins
        if all_plugins:
            from cod3s_data.broker.in_memory import InMemoryBroker
            from cod3s_data.config.factory import ComponentFactory
            from cod3s_data.plugins import load_plugins

            broker = InMemoryBroker()
            factory = ComponentFactory(broker)
            load_plugins(all_plugins, factory)

            # Verify all referenced types exist
            for source in config.sources:
                if source.type not in factory.registered_source_types:
                    raise ValueError(f"Unknown source type '{source.type}'")
            for transform in config.transformations:
                if transform.type not in factory.registered_transformation_types:
                    raise ValueError(f"Unknown transformation type '{transform.type}'")
            for dest in config.destinations:
                if dest.type not in factory.registered_destination_types:
                    raise ValueError(f"Unknown destination type '{dest.type}'")

        # Print configuration summary
        print("\n✓ Configuration is valid!")
        print(f"\nPipeline: {config.name}")
        print(f"  Plugins: {len(all_plugins)}")
        print(f"  Sources: {len(config.sources)}")
        for i, source in enumerate(config.sources, 1):
            print(f"    {i}. {source.type} -> {source.channel}")

        print(f"  Transformations: {len(config.transformations)}")
        for i, transform in enumerate(config.transformations, 1):
            print(
                f"    {i}. {transform.type}: {transform.input_channels} -> {transform.output_channel}"
            )

        print(f"  Destinations: {len(config.destinations)}")
        for i, dest in enumerate(config.destinations, 1):
            print(f"    {i}. {dest.type} <- {dest.channel_pattern}")

        return 0

    except Exception as e:
        print("\n✗ Configuration is invalid!", file=sys.stderr)
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        prog="cod3s-data",
        description="COD3S Data Framework - Lightweight data streaming framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--version",
        action="version",
        version="COD3S Data Framework v1.0.0",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run a pipeline from configuration file",
    )
    run_parser.add_argument(
        "config",
        help="Path to pipeline configuration file (YAML)",
    )
    run_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )
    run_parser.add_argument(
        "--json-logs",
        action="store_true",
        help="Output logs in JSON format (default: console format)",
    )
    run_parser.add_argument(
        "-p",
        "--plugin",
        action="append",
        default=None,
        help="Plugin module path to load (repeatable)",
    )
    run_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output (show stack traces on error)",
    )
    run_parser.add_argument(
        "--observatory",
        action="store_true",
        help="Enable Observatory web UI for debugging and monitoring",
    )
    run_parser.add_argument(
        "--observatory-port",
        type=int,
        default=None,
        help="Observatory server port (default: 8765)",
    )
    run_parser.add_argument(
        "--interactive",
        action="store_true",
        help="Start Observatory in interactive mode (pipeline waits for UI to start it)",
    )
    run_parser.set_defaults(func=run_pipeline)

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a pipeline configuration file",
    )
    validate_parser.add_argument(
        "config",
        help="Path to pipeline configuration file (YAML)",
    )
    validate_parser.add_argument(
        "-p",
        "--plugin",
        action="append",
        default=None,
        help="Plugin module path to load (repeatable)",
    )
    validate_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output (show stack traces on error)",
    )
    validate_parser.set_defaults(func=validate_pipeline)

    # Parse arguments
    args = parser.parse_args()

    # Show help if no command provided
    if not args.command:
        parser.print_help()
        return 1

    # Execute command
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
