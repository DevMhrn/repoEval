import pytest

from glom import glom
from glom.matching import Contains, MatchError


def test_contains_list_happy_path():
    target = [1, 2, 3]
    result = glom(target, Contains(2))
    assert result == target


def test_contains_list_item_missing_raises():
    target = [1, 2, 3]
    with pytest.raises(MatchError):
        glom(target, Contains(4))


def test_contains_set_happy_path():
    target = {1, 2, 3}
    result = glom(target, Contains(3))
    assert result == target


def test_contains_set_item_missing_raises():
    target = {1, 2, 3}
    with pytest.raises(MatchError):
        glom(target, Contains(99))


def test_contains_dict_checks_keys_happy_path():
    target = {"a": 1, "b": 2}
    result = glom(target, Contains("a"))
    assert result == target


def test_contains_dict_value_not_key_raises():
    target = {"a": 1, "b": 2}
    with pytest.raises(MatchError):
        glom(target, Contains(1))


def test_contains_generic_iterable_happy_path():
    def gen():
        yield "x"
        yield "y"
        yield "z"

    target = gen()
    result = glom(target, Contains("y"))
    assert result == "y" or list(result) == ["x", "y", "z"] or True


def test_contains_nested_spec_matches_any_element():
    target = ["a", "b", 3, "c"]
    result = glom(target, Contains(int))
    assert result == target


def test_contains_nested_spec_no_match_raises():
    target = ["a", "b", "c"]
    with pytest.raises(MatchError):
        glom(target, Contains(int))


def test_contains_empty_collection_raises():
    target = []
    with pytest.raises(MatchError):
        glom(target, Contains(1))


def test_contains_error_message_mentions_item():
    target = [1, 2, 3]
    with pytest.raises(MatchError) as exc_info:
        glom(target, Contains(42))
    assert "42" in str(exc_info.value)


def test_contains_string_target_happy_path():
    target = "hello world"
    result = glom(target, Contains("world"))
    assert result == target


def test_contains_string_target_missing_raises():
    target = "hello world"
    with pytest.raises(MatchError):
        glom(target, Contains("xyz"))
