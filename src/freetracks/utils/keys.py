"""Musical key <-> Camelot wheel conversion and harmonic mixing utilities.

The Camelot wheel is the standard system DJs use for harmonic mixing.
Adjacent keys on the wheel (same number ±1, or same number A<->B) are
harmonically compatible and can be mixed smoothly.
"""

# Standard key -> Camelot mapping
_STANDARD_TO_CAMELOT: dict[str, str] = {
    # Minor keys (A side)
    "Abm": "1A", "G#m": "1A",
    "Ebm": "2A", "D#m": "2A",
    "Bbm": "3A", "A#m": "3A",
    "Fm": "4A",
    "Cm": "5A",
    "Gm": "6A",
    "Dm": "7A",
    "Am": "8A",
    "Em": "9A",
    "Bm": "10A",
    "F#m": "11A", "Gbm": "11A",
    "Dbm": "12A", "C#m": "12A",
    # Major keys (B side)
    "B": "1B",
    "F#": "2B", "Gb": "2B",
    "Db": "3B", "C#": "3B",
    "Ab": "4B", "G#": "4B",
    "Eb": "5B", "D#": "5B",
    "Bb": "6B", "A#": "6B",
    "F": "7B",
    "C": "8B",
    "G": "9B",
    "D": "10B",
    "A": "11B",
    "E": "12B",
}

# Reverse mapping: Camelot -> standard key (canonical names only)
_CAMELOT_TO_STANDARD: dict[str, str] = {
    "1A": "Abm", "2A": "Ebm", "3A": "Bbm", "4A": "Fm",
    "5A": "Cm", "6A": "Gm", "7A": "Dm", "8A": "Am",
    "9A": "Em", "10A": "Bm", "11A": "F#m", "12A": "C#m",
    "1B": "B", "2B": "F#", "3B": "Db", "4B": "Ab",
    "5B": "Eb", "6B": "Bb", "7B": "F", "8B": "C",
    "9B": "G", "10B": "D", "11B": "A", "12B": "E",
}

# Open Key notation mapping (another system some DJs use)
_OPEN_KEY_TO_CAMELOT: dict[str, str] = {
    "1m": "10A", "2m": "11A", "3m": "12A", "4m": "1A",
    "5m": "2A", "6m": "3A", "7m": "4A", "8m": "5A",
    "9m": "6A", "10m": "7A", "11m": "8A", "12m": "9A",
    "1d": "10B", "2d": "11B", "3d": "12B", "4d": "1B",
    "5d": "2B", "6d": "3B", "7d": "4B", "8d": "5B",
    "9d": "6B", "10d": "7B", "11d": "8B", "12d": "9B",
}


def normalize_key(key_str: str) -> str | None:
    """Normalize a key string to canonical standard notation.

    Handles variations like:
        'a minor' -> 'Am'
        'A min'   -> 'Am'
        'a'       -> 'Am' (lowercase = minor by convention in some platforms)
        'C major' -> 'C'
        'C maj'   -> 'C'
        'Cmaj'    -> 'C'
        'Cmin'    -> 'Cm'
        '8A'      -> 'Am' (Camelot)
    """
    if not key_str or not key_str.strip():
        return None

    s = key_str.strip()

    # Check if it's already Camelot notation
    upper = s.upper()
    if upper in _CAMELOT_TO_STANDARD:
        return _CAMELOT_TO_STANDARD[upper]

    # Check Open Key notation
    lower = s.lower()
    if lower in _OPEN_KEY_TO_CAMELOT:
        camelot = _OPEN_KEY_TO_CAMELOT[lower]
        return _CAMELOT_TO_STANDARD[camelot]

    # Handle word forms: "A minor", "C major", "F# min", "Bb maj"
    for minor_suffix in (" minor", " min"):
        if lower.endswith(minor_suffix):
            root = s[: -len(minor_suffix)].strip()
            return _capitalize_root(root) + "m"
    for major_suffix in (" major", " maj"):
        if lower.endswith(major_suffix):
            root = s[: -len(major_suffix)].strip()
            return _capitalize_root(root)

    # Handle "Cmaj", "Cmin", "Cmajor", "Cminor"
    if lower.endswith("minor"):
        root = s[:-5]
        return _capitalize_root(root) + "m"
    if lower.endswith("major"):
        root = s[:-5]
        return _capitalize_root(root)
    if lower.endswith("min"):
        root = s[:-3]
        return _capitalize_root(root) + "m"
    if lower.endswith("maj"):
        root = s[:-3]
        return _capitalize_root(root)

    # Direct lookup
    if s in _STANDARD_TO_CAMELOT:
        return s

    # Try capitalizing
    cap = _capitalize_root(s)
    if cap in _STANDARD_TO_CAMELOT:
        return cap

    # If single lowercase letter, some platforms use lowercase for minor
    if len(s) == 1 and s.isalpha():
        candidate = s.upper() + "m"
        if candidate in _STANDARD_TO_CAMELOT:
            return candidate

    return s  # Return as-is if we can't parse it


def _capitalize_root(root: str) -> str:
    """Capitalize a key root: 'ab' -> 'Ab', 'f#' -> 'F#', 'bb' -> 'Bb'."""
    if not root:
        return root
    result = root[0].upper()
    if len(root) > 1:
        result += root[1:]
    return result


def standard_to_camelot(key: str) -> str | None:
    """Convert standard key notation to Camelot. Returns None if unrecognized."""
    normalized = normalize_key(key)
    if normalized is None:
        return None
    return _STANDARD_TO_CAMELOT.get(normalized)


def camelot_to_standard(camelot: str) -> str | None:
    """Convert Camelot notation to standard key. Returns None if unrecognized."""
    return _CAMELOT_TO_STANDARD.get(camelot.upper())


def get_compatible_keys(key: str) -> list[str]:
    """Get harmonically compatible keys for mixing (Camelot wheel neighbors).

    Compatible keys are:
    - Same position (identical key)
    - ±1 on the wheel (adjacent number, same letter)
    - Same number, opposite letter (relative major/minor)

    Returns list of Camelot keys.
    """
    camelot = standard_to_camelot(key) if key not in _CAMELOT_TO_STANDARD else key.upper()
    if camelot is None:
        return []

    number = int(camelot[:-1])
    letter = camelot[-1]

    compatible = [camelot]

    # Same number, other side (relative major/minor)
    other_letter = "B" if letter == "A" else "A"
    compatible.append(f"{number}{other_letter}")

    # ±1 on the wheel (wraps around 12)
    prev_num = 12 if number == 1 else number - 1
    next_num = 1 if number == 12 else number + 1
    compatible.append(f"{prev_num}{letter}")
    compatible.append(f"{next_num}{letter}")

    return compatible
