from src.picker.names import NAMED_COLORS, XKCD_OVERRIDES


def test_named_colors_count():
    assert len(NAMED_COLORS) == 987


def test_css_names_are_authoritative():
    assert NAMED_COLORS["red"] == "#ff0000"
    assert NAMED_COLORS["gray"] == "#808080"
    assert NAMED_COLORS["midnightblue"] == "#191970"
    assert NAMED_COLORS["aliceblue"] == "#f0f8ff"


def test_xkcd_only_names_present():
    assert NAMED_COLORS["emerald"] == "#01a049"
    assert NAMED_COLORS["seafoam"] == "#80f9ad"


def test_dropped_x11_variants_absent():
    assert "gray50" not in NAMED_COLORS
    assert "webgray" not in NAMED_COLORS
    assert "azure1" not in NAMED_COLORS


def test_overrides_are_a_subset_of_named_colors():
    assert len(XKCD_OVERRIDES) == 92
    for name, hex_val in XKCD_OVERRIDES.items():
        assert name in NAMED_COLORS
        assert NAMED_COLORS[name] != hex_val


def test_named_colors_all_valid_hex():
    import re
    for name, hex_val in NAMED_COLORS.items():
        assert re.match(r"^#[0-9a-f]{6}$", hex_val), f"{name}={hex_val}"


def test_keys_are_normalized():
    for name in NAMED_COLORS:
        assert name == name.lower()
        assert " " not in name and "-" not in name and "'" not in name


def test_both_generated_files_agree():
    """hued-names.sh and names.py must come from the same generator run."""
    import pathlib
    import re
    sh = pathlib.Path(__file__).resolve().parents[2] / "hued-names.sh"
    plain, override = {}, {}
    for line in sh.read_text().splitlines():
        m = re.match(r"\s*\[(?:(xkcd):)?([^\]]+)\]=(#[0-9a-f]{6})", line)
        if m:
            (override if m.group(1) else plain)[m.group(2)] = m.group(3)
    assert plain == NAMED_COLORS
    assert override == XKCD_OVERRIDES
