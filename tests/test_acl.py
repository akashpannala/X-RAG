"""ACL unit tests — fail-closed empty groups; sparse hits must carry allowed_groups."""
from backend.l14_security.acl import allowed, groups_filter


def test_groups_filter_shape():
    f = groups_filter(["hr", "public"])
    assert f.must[0].key == "allowed_groups"
    assert list(f.must[0].match.any) == ["hr", "public"]


def test_allowed_intersection():
    assert allowed(["hr", "public"], ["hr"])
    assert allowed(["eng"], ["eng", "public"])
    assert not allowed(["eng"], ["hr"])


def test_allowed_empty_request_groups_fail_closed():
    assert not allowed([], ["public"])
    assert not allowed([], ["hr"])


def test_allowed_legacy_hit_defaults_public():
    # missing allowed_groups on a hit → treated as public
    assert allowed(["public"], None)
    assert allowed(["public"], [])
    assert not allowed(["hr"], None)


def test_allowed_no_overlap():
    assert not allowed(["hr"], ["eng", "public"])
