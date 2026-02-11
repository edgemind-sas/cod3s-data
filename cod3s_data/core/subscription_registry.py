"""Efficient channel pattern matching for pub/sub subscriptions."""

import re
from collections import defaultdict
from typing import Awaitable, Callable

from cod3s_data.core.message import Message

# Type alias for callback function
Callback = Callable[[Message], Awaitable[None]]


class SubscriptionRegistry:
    """
    Efficient channel pattern matching for pub/sub.

    Performance:
    - Exact matches: O(1)
    - Single-level wildcards: O(n) where n = number of * patterns
    - Multi-level wildcards: O(m) where m = number of ** patterns

    Typical: <1ms for 100 subscriptions
    """

    def __init__(self) -> None:
        """Initialize the subscription registry."""
        # Exact matches: O(1) lookup
        self._exact_matches: dict[str, list[Callback]] = defaultdict(list)

        # Single-level wildcards: sensors.*.temp
        self._single_wildcards: dict[re.Pattern[str], list[Callback]] = {}

        # Multi-level wildcards: sensors.**
        self._multi_wildcards: list[tuple[re.Pattern[str], Callback]] = []

    def add_subscription(self, pattern: str, callback: Callback) -> None:
        """
        Register a subscription with channel pattern.

        Args:
            pattern: Channel pattern (exact or with wildcards)
                - Exact: "sensors.temp"
                - Single-level: "sensors.*.temp" (one level only)
                - Multi-level: "sensors.**" (zero or more levels)
            callback: Async function to call when channel matches

        Examples:
            >>> async def my_callback(msg: Message):
            ...     print(f"Received: {msg.value}")
            >>> registry.add_subscription("sensors.temp", my_callback)
            >>> registry.add_subscription("sensors.*.temp", my_callback)
            >>> registry.add_subscription("alerts.**", my_callback)
        """
        if "*" not in pattern:
            # Exact match: store in dictionary
            self._exact_matches[pattern].append(callback)

        elif "**" in pattern:
            # Multi-level wildcard
            regex = self._compile_multi_wildcard(pattern)
            self._multi_wildcards.append((regex, callback))

        else:
            # Single-level wildcard
            regex = self._compile_single_wildcard(pattern)
            if regex not in self._single_wildcards:
                self._single_wildcards[regex] = []
            self._single_wildcards[regex].append(callback)

    def match_channel(self, channel: str) -> list[Callback]:
        """
        Return all callbacks matching this channel.

        Args:
            channel: Exact channel name (e.g., "sensors.printer1.temp")

        Returns:
            List of callbacks to invoke (may be empty)

        Performance:
            - Best case (exact match): O(1)
            - Worst case (no exact, check wildcards): O(n + m)
              where n = single wildcards, m = multi wildcards
            - Typical: <1ms for 100 subscriptions

        Examples:
            >>> callbacks = registry.match_channel("sensors.printer1.temp")
            >>> for cb in callbacks:
            ...     await cb(message)
        """
        callbacks: list[Callback] = []

        # 1. Check exact match first (fast path)
        if channel in self._exact_matches:
            callbacks.extend(self._exact_matches[channel])

        # 2. Check single-level wildcards
        for pattern, cbs in self._single_wildcards.items():
            if pattern.fullmatch(channel):
                callbacks.extend(cbs)

        # 3. Check multi-level wildcards
        for pattern, cb in self._multi_wildcards:
            if pattern.fullmatch(channel):
                callbacks.append(cb)

        return callbacks

    def remove_subscription(self, pattern: str, callback: Callback) -> None:
        """
        Remove a specific subscription.

        Args:
            pattern: Original pattern used in add_subscription
            callback: Exact callback to remove

        Examples:
            >>> registry.remove_subscription("sensors.temp", my_callback)
        """
        if "*" not in pattern:
            if pattern in self._exact_matches:
                try:
                    self._exact_matches[pattern].remove(callback)
                    if not self._exact_matches[pattern]:
                        del self._exact_matches[pattern]
                except ValueError:
                    pass  # Callback not found

        elif "**" in pattern:
            regex = self._compile_multi_wildcard(pattern)
            self._multi_wildcards = [
                (p, cb)
                for p, cb in self._multi_wildcards
                if not (p.pattern == regex.pattern and cb == callback)
            ]

        else:
            regex = self._compile_single_wildcard(pattern)
            if regex in self._single_wildcards:
                try:
                    self._single_wildcards[regex].remove(callback)
                    if not self._single_wildcards[regex]:
                        del self._single_wildcards[regex]
                except ValueError:
                    pass

    @staticmethod
    def _compile_single_wildcard(pattern: str) -> re.Pattern[str]:
        r"""
        Compile single-level wildcard pattern to regex.

        Pattern: "sensors.*.temp"
        Regex: ^sensors\.[^.]+\.temp$

        Args:
            pattern: Pattern with single-level wildcards (*)

        Returns:
            Compiled regex pattern
        """
        # Escape special regex characters except *
        escaped = re.escape(pattern)

        # Replace \* with [^.]+ (one or more non-dot characters)
        regex_pattern = escaped.replace(r"\*", r"[^.]+")

        # Anchor to full string
        regex_pattern = f"^{regex_pattern}$"

        return re.compile(regex_pattern)

    @staticmethod
    def _compile_multi_wildcard(pattern: str) -> re.Pattern[str]:
        r"""
        Compile multi-level wildcard pattern to regex.

        Pattern: "sensors.**"
        Matches: sensors, sensors.temp, sensors.a.b.temp

        Pattern: "**.temp"
        Matches: temp, a.temp, a.b.temp

        Pattern: "sensors.**.temp"
        Matches: sensors.temp, sensors.a.temp, sensors.a.b.temp

        Args:
            pattern: Pattern with multi-level wildcards (**)

        Returns:
            Compiled regex pattern
        """
        parts = pattern.split("**")

        if len(parts) == 2:
            # Single ** (most common case)
            prefix, suffix = parts

            # Escape the prefix and suffix
            prefix_esc = re.escape(prefix)
            suffix_esc = re.escape(suffix)

            if prefix and suffix:
                # Middle: "sensors.**.temp" -> "sensors." + (.*\.)? + "temp"
                # The (.*\.)? allows zero or more intermediate levels
                # Remove trailing dot from prefix and leading dot from suffix
                if prefix.endswith("."):
                    prefix_esc = prefix_esc[:-2]  # Remove \. at end
                if suffix.startswith("."):
                    suffix_esc = suffix_esc[2:]  # Remove \. at start
                regex_pattern = f"^{prefix_esc}(\\..*)?\\.{suffix_esc}$"
            elif prefix:
                # Suffix wildcard: "sensors.**" -> "sensors" + (\..*)?
                # Remove trailing dot from prefix if present
                if prefix.endswith("."):
                    prefix_esc = prefix_esc[:-2]  # Remove \. at end
                    regex_pattern = f"^{prefix_esc}(\\..*)?$"
                else:
                    regex_pattern = f"^{prefix_esc}$"
            else:
                # Prefix wildcard: "**.temp" -> (.*\.)? + "temp"
                # Remove leading dot from suffix if present
                if suffix.startswith("."):
                    suffix_esc = suffix_esc[2:]  # Remove \. at start
                    regex_pattern = f"^(.*\\.)?{suffix_esc}$"
                else:
                    regex_pattern = f"^{suffix_esc}$"
        else:
            # Multiple ** or edge cases - just replace all
            escaped = re.escape(pattern)
            regex_pattern = f"^{escaped.replace(r'\\*\\*', '.*')}$"

        return re.compile(regex_pattern)

    @staticmethod
    def matches(pattern: str, channel: str) -> bool:
        """Test if a channel matches a pattern.

        Args:
            pattern: Channel pattern (exact, single-wildcard *, or multi-wildcard **)
            channel: Exact channel name

        Returns:
            True if the channel matches the pattern.
        """
        if "*" not in pattern:
            return pattern == channel
        if "**" in pattern:
            regex = SubscriptionRegistry._compile_multi_wildcard(pattern)
        else:
            regex = SubscriptionRegistry._compile_single_wildcard(pattern)
        return regex.fullmatch(channel) is not None

    def get_all_patterns(self) -> list[str]:
        """
        Get all registered patterns (for debugging).

        Returns:
            List of all channel patterns
        """
        patterns = list(self._exact_matches.keys())

        for regex in self._single_wildcards.keys():
            patterns.append(regex.pattern)

        for regex, _ in self._multi_wildcards:
            patterns.append(regex.pattern)

        return patterns

    def count_subscriptions(self) -> int:
        """
        Total number of subscriptions.

        Returns:
            Count of all subscriptions
        """
        count = sum(len(cbs) for cbs in self._exact_matches.values())
        count += sum(len(cbs) for cbs in self._single_wildcards.values())
        count += len(self._multi_wildcards)
        return count
