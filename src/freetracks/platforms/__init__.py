"""Platform registry — central place to get scanner instances."""

from freetracks.platforms.base import PlatformScanner
from freetracks.platforms.soundcloud import SoundCloudScanner
from freetracks.platforms.bandcamp import BandcampScanner
from freetracks.platforms.hypeddit import HypedditScanner

# Registry of all available platform scanners
PLATFORM_SCANNERS: dict[str, type[PlatformScanner]] = {
    "soundcloud": SoundCloudScanner,
    "bandcamp": BandcampScanner,
    "hypeddit": HypedditScanner,
}

PLATFORM_NAMES = list(PLATFORM_SCANNERS.keys())


def get_scanner(platform: str, **kwargs) -> PlatformScanner:
    """Get a scanner instance by platform name.

    Args:
        platform: Platform name (soundcloud, bandcamp, hypeddit)
        **kwargs: Passed to the scanner constructor

    Returns:
        Configured PlatformScanner instance.

    Raises:
        ValueError: If the platform name is not recognized.
    """
    scanner_cls = PLATFORM_SCANNERS.get(platform.lower())
    if scanner_cls is None:
        available = ", ".join(PLATFORM_NAMES)
        raise ValueError(f"Unknown platform '{platform}'. Available: {available}")
    return scanner_cls(**kwargs)


def get_all_scanners(**kwargs) -> list[PlatformScanner]:
    """Get scanner instances for all registered platforms."""
    return [cls(**kwargs) for cls in PLATFORM_SCANNERS.values()]


__all__ = [
    "PlatformScanner",
    "SoundCloudScanner",
    "BandcampScanner",
    "HypedditScanner",
    "PLATFORM_SCANNERS",
    "PLATFORM_NAMES",
    "get_scanner",
    "get_all_scanners",
]
