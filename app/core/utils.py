"""
Utility functions for the nalssi application.
"""

import re
import unicodedata


def slugify(text: str) -> str:
    """
    Convert text to a URL/key-friendly slug.

    - Converts to lowercase
    - Normalizes unicode characters to ASCII equivalents
    - Replaces non-alphanumeric characters with underscores
    - Collapses multiple underscores
    - Strips leading/trailing underscores

    Args:
        text: The text to slugify

    Returns:
        A slug string suitable for use in keys and URLs

    Examples:
        >>> slugify("San Francisco, CA")
        'san_francisco_ca'
        >>> slugify("Spring Hill")
        'spring_hill'
        >>> slugify("  Hello   World  ")
        'hello_world'
    """
    # Normalize unicode to ASCII equivalents (e.g., é -> e)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    # Lowercase
    text = text.lower()
    # Replace non-alphanumeric characters with underscores
    text = re.sub(r"[^a-z0-9]+", "_", text)
    # Strip leading/trailing underscores
    text = text.strip("_")
    return text
