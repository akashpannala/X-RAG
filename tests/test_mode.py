"""Quick/Deep mode resolution + role defaults."""
from backend.l09_toggle.mode import resolve
from backend.l14_security.auth import default_mode


def test_default_mode_by_group():
    assert default_mode(["hr"]) == "quick"
    assert default_mode(["eng"]) == "deep"
    assert default_mode(["public"]) == "quick"
    # first matching group in list wins
    assert default_mode(["eng", "hr"]) == "deep"
    assert default_mode(["hr", "eng"]) == "quick"
    assert default_mode([]) == "quick"
    assert default_mode(["unknown"]) == "quick"


def test_resolve_override_valid():
    assert resolve(["hr"], "deep") == "deep"
    assert resolve(["eng"], "quick") == "quick"


def test_resolve_invalid_override_falls_back():
    assert resolve(["hr"], "string") == "quick"
    assert resolve(["eng"], "string") == "deep"
    assert resolve(["hr"], None) == "quick"
