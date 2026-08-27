import pytest

from glom import glom
from glom.matching import Length, Match, And, Or, CheckError


def test_length_exact_match_success():
    assert glom([1, 2, 3], Length(3)) == [1, 2, 3]


def test_length_exact_match_failure():
    with pytest.raises(CheckError):
        glom([1, 2], Length(3))


def test_length_min_max_success():
    assert glom("hello", Length(min=1, max=10)) == "hello"


def test_length_min_only_success():
    assert glom([1, 2, 3, 4], Length(min=2)) == [1, 2, 3, 4]


def test_length_min_only_failure_too_short():
    with pytest.raises(CheckError):
        glom("", Length(min=1))


def test_length_max_only_failure_too_long():
    with pytest.raises(CheckError):
        glom(list(range(20)), Length(max=10))


def test_length_min_max_boundaries_inclusive():
    assert glom([1], Length(min=1, max=1)) == [1]
    assert glom([1, 2, 3], Length(min=1, max=3)) == [1, 2, 3]


def test_length_with_and_combinator_success():
    spec = And(Length(min=2), Length(max=5))
    assert glom([1, 2, 3], spec) == [1, 2, 3]


def test_length_with_and_combinator_failure():
    spec = And(Length(min=2), Length(max=5))
    with pytest.raises(CheckError):
        glom([1], spec)


def test_length_with_or_combinator_success():
    spec = Or(Length(0), Length(5))
    assert glom([], spec) == []
    assert glom([1, 2, 3, 4, 5], spec) == [1, 2, 3, 4, 5]


def test_length_with_or_combinator_failure():
    spec = Or(Length(0), Length(5))
    with pytest.raises(CheckError):
        glom([1, 2], spec)


def test_length_within_match_spec_success():
    spec = Match(Length(min=1))
    assert glom([1], spec) == [1]


def test_length_within_match_spec_failure():
    spec = Match(Length(min=1))
    with pytest.raises(CheckError):
        glom([], spec)


def test_length_error_message_mentions_length():
    try:
        glom([1], Length(5))
    except CheckError as exc:
        message = str(exc).lower()
        assert "length" in message or "len" in message
    else:
        pytest.fail("CheckError was not raised")


def test_length_edge_case_empty_target_zero_length():
    assert glom("", Length(0)) == ""
    assert glom("", Length(max=0)) == ""


def test_length_edge_case_zero_min_allows_empty():
    assert glom([], Length(min=0)) == []


def test_length_non_sized_target_raises_check_error():
    with pytest.raises(CheckError):
        glom(42, Length(1))
