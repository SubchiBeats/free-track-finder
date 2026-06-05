"""Formatting utilities for human-readable display of track metadata."""


def format_duration(seconds: float | int | None) -> str:
    """Format seconds into M:SS or H:MM:SS."""
    if seconds is None:
        return "—"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_file_size(size_bytes: int | None) -> str:
    """Format bytes into human-readable size."""
    if size_bytes is None:
        return "—"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_number(n: int | None) -> str:
    """Format a number with comma separators."""
    if n is None:
        return "—"
    return f"{n:,}"


def truncate(text: str, max_length: int = 40) -> str:
    """Truncate text with ellipsis if it exceeds max length."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"
