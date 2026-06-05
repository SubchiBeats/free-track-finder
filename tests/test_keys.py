"""Tests for musical key / Camelot wheel utilities."""


from freetracks.utils.keys import (
    camelot_to_standard,
    get_compatible_keys,
    normalize_key,
    standard_to_camelot,
)


class TestStandardToCamelot:
    def test_minor_keys(self):
        assert standard_to_camelot("Am") == "8A"
        assert standard_to_camelot("Cm") == "5A"
        assert standard_to_camelot("Dm") == "7A"
        assert standard_to_camelot("Em") == "9A"
        assert standard_to_camelot("Fm") == "4A"
        assert standard_to_camelot("Gm") == "6A"
        assert standard_to_camelot("Bm") == "10A"

    def test_major_keys(self):
        assert standard_to_camelot("C") == "8B"
        assert standard_to_camelot("D") == "10B"
        assert standard_to_camelot("G") == "9B"
        assert standard_to_camelot("F") == "7B"
        assert standard_to_camelot("A") == "11B"

    def test_sharp_flat_keys(self):
        assert standard_to_camelot("F#m") == "11A"
        assert standard_to_camelot("Bbm") == "3A"
        assert standard_to_camelot("Ebm") == "2A"
        assert standard_to_camelot("Ab") == "4B"
        assert standard_to_camelot("Db") == "3B"

    def test_enharmonic_equivalents(self):
        assert standard_to_camelot("G#m") == "1A"
        assert standard_to_camelot("Abm") == "1A"
        assert standard_to_camelot("D#m") == "2A"
        assert standard_to_camelot("A#m") == "3A"

    def test_unknown_key(self):
        assert standard_to_camelot("Xm") is None
        assert standard_to_camelot("") is None


class TestCamelotToStandard:
    def test_a_side(self):
        assert camelot_to_standard("8A") == "Am"
        assert camelot_to_standard("5A") == "Cm"
        assert camelot_to_standard("1A") == "Abm"

    def test_b_side(self):
        assert camelot_to_standard("8B") == "C"
        assert camelot_to_standard("1B") == "B"
        assert camelot_to_standard("7B") == "F"

    def test_case_insensitive(self):
        assert camelot_to_standard("8a") == "Am"
        assert camelot_to_standard("8b") == "C"


class TestNormalizeKey:
    def test_standard_notation(self):
        assert normalize_key("Am") == "Am"
        assert normalize_key("C") == "C"
        assert normalize_key("F#m") == "F#m"

    def test_word_forms(self):
        assert normalize_key("A minor") == "Am"
        assert normalize_key("C major") == "C"
        assert normalize_key("F# minor") == "F#m"
        assert normalize_key("Bb major") == "Bb"

    def test_abbreviated_word_forms(self):
        assert normalize_key("A min") == "Am"
        assert normalize_key("C maj") == "C"
        assert normalize_key("Amin") == "Am"
        assert normalize_key("Cmaj") == "C"

    def test_camelot_input(self):
        assert normalize_key("8A") == "Am"
        assert normalize_key("8B") == "C"
        assert normalize_key("11A") == "F#m"

    def test_empty_input(self):
        assert normalize_key("") is None
        assert normalize_key("  ") is None


class TestCompatibleKeys:
    def test_compatible_with_8a(self):
        # Am (8A) should be compatible with: 8A, 8B, 7A, 9A
        compatible = get_compatible_keys("Am")
        assert "8A" in compatible
        assert "8B" in compatible  # Relative major (C)
        assert "7A" in compatible  # Dm
        assert "9A" in compatible  # Em
        assert len(compatible) == 4

    def test_wrap_around(self):
        # 1A should wrap to 12A
        compatible = get_compatible_keys("1A")
        assert "12A" in compatible
        assert "2A" in compatible

    def test_wrap_around_12(self):
        # 12A should wrap to 1A
        compatible = get_compatible_keys("12A")
        assert "11A" in compatible
        assert "1A" in compatible
