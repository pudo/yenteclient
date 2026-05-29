import pytest

from yente_client.schemas import (
    has_schema,
    is_a,
    is_deprecated,
    iter_properties,
    model,
)


def test_model_loaded() -> None:
    assert "schemata" in model
    assert "types" in model
    assert "Person" in model["schemata"]
    assert "topic" in model["types"]


def test_person_property_type() -> None:
    assert model["schemata"]["Person"]["properties"]["birthDate"]["type"] == "date"


def test_topic_enum_has_sanction() -> None:
    assert "sanction" in model["types"]["topic"]["values"]


def test_has_schema() -> None:
    assert has_schema("Person") is True
    assert has_schema("Company") is True
    assert has_schema("Thing") is True
    assert has_schema("NotARealSchema") is False


def test_is_a_inheritance() -> None:
    assert is_a("Person", "Thing") is True
    assert is_a("Person", "LegalEntity") is True
    assert is_a("LegalEntity", "Thing") is True
    assert is_a("Address", "Thing") is True


def test_is_a_reflexive() -> None:
    assert is_a("Person", "Person") is True


def test_is_a_negative() -> None:
    assert is_a("Address", "LegalEntity") is False
    assert is_a("Person", "Company") is False


def test_is_a_unknown_schema_raises() -> None:
    with pytest.raises(KeyError):
        is_a("NotARealSchema", "Thing")


def test_iter_properties_flattens_inheritance() -> None:
    props = set(iter_properties("Person"))
    # Person's own:
    assert "firstName" in props
    assert "lastName" in props
    assert "birthDate" in props
    # Inherited from LegalEntity:
    assert "name" in props
    assert "jurisdiction" in props
    # Inherited from Thing:
    assert "topics" in props


def test_iter_properties_unique() -> None:
    props = list(iter_properties("Person"))
    assert len(props) == len(set(props)), "iter_properties yielded duplicates"


def test_iter_properties_unknown_raises() -> None:
    with pytest.raises(KeyError):
        list(iter_properties("NotARealSchema"))


def test_is_deprecated_true_own_property() -> None:
    assert is_deprecated("Person", "secondName") is True


def test_is_deprecated_false_active_property() -> None:
    assert is_deprecated("Person", "firstName") is False
    assert is_deprecated("Person", "birthDate") is False


def test_is_deprecated_inherited_deprecation() -> None:
    # LegalEntity.parent is deprecated; Person inherits it transitively.
    assert is_deprecated("Person", "parent") is True


def test_is_deprecated_unknown_schema_raises() -> None:
    with pytest.raises(KeyError):
        is_deprecated("NotARealSchema", "anything")


def test_is_deprecated_unknown_property_raises() -> None:
    with pytest.raises(KeyError):
        is_deprecated("Person", "noSuchProperty")
