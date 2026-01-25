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

        # Run pipeline
        print(f"Starting pipeline: {config.name}")

        async def run():
            async with Framework(config) as framework:
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

        # Print configuration summary
        print("\n✓ Configuration is valid!")
        print(f"\nPipeline: {config.name}")
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
        print(f"\n✗ Configuration is invalid!", file=sys.stderr)
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
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output (show stack traces on error)",
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
