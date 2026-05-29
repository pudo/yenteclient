"""Tests for the codegen-emitted per-schema entity classes."""

import pytest
from pydantic import ValidationError

from yente_client.entities import Company, Email, Person
from yente_client.entities._base import _EntityBase
from yente_client.schemas._literals import Gender, PropertyType, Schema, Topic


def test_person_construction_and_payload() -> None:
    p = Person(firstName="Aleksandr", lastName="Zacharov", birthDate="1965")
    assert p.firstName == ["Aleksandr"]
    assert p.lastName == ["Zacharov"]
    assert p.birthDate == ["1965"]
    payload = p.to_payload()
    assert payload == {
        "schema": "Person",
        "properties": {
            "birthDate": ["1965"],
            "firstName": ["Aleksandr"],
            "lastName": ["Zacharov"],
        },
    }


def test_person_inherited_properties_present() -> None:
    # `name` and `country` come from LegalEntity; `topics` from Thing.
    p = Person(name=["Aleksandr Zacharov"], country="ru", topics=["sanction"])
    assert p.name == ["Aleksandr Zacharov"]
    assert p.country == ["ru"]
    assert p.topics == ["sanction"]


def test_person_str_to_list_coercion() -> None:
    p = Person(firstName="X")
    assert p.firstName == ["X"]


def test_person_unknown_property_rejected() -> None:
    with pytest.raises(ValidationError):
        Person(notAProperty="X")


def test_person_snake_case_rejected() -> None:
    # camelCase is canonical; snake_case is not aliased to anything.
    with pytest.raises(ValidationError):
        Person(first_name="X")


def test_person_classvar_schema() -> None:
    assert Person.schema_ == "Person"
    assert Person(firstName="X").schema_ == "Person"


def test_company_distinct_from_person() -> None:
    c = Company(name="Acme LLC", jurisdiction="us")
    assert c.schema_ == "Company"
    assert c.to_payload()["schema"] == "Company"
    # Property only on Company, not Person:
    assert "jurisdiction" in c.to_payload()["properties"]


def test_email_keyword_escape_via_alias() -> None:
    # `from` is a Python keyword so the field is `from_` with alias="from".
    e = Email(from_="alice@x.com", to="bob@y.com")
    assert e.from_ == ["alice@x.com"]
    payload = e.to_payload()
    # On the wire we send the alias.
    assert payload["properties"]["from"] == ["alice@x.com"]
    assert "from_" not in payload["properties"]


def test_email_keyword_escape_via_alias_dict() -> None:
    # Also accept the wire-format alias via model_validate.
    e = Email.model_validate({"from": ["alice@x.com"]})
    assert e.from_ == ["alice@x.com"]


def test_isinstance_entity_base() -> None:
    assert isinstance(Person(firstName="X"), _EntityBase)
    assert isinstance(Company(name="Acme"), _EntityBase)
    assert isinstance(Email(from_="a@b.com"), _EntityBase)


def test_to_payload_drops_empty_properties() -> None:
    # Only fields the caller set should appear; empty defaults are omitted.
    p = Person(firstName="X")
    payload = p.to_payload()
    assert payload["properties"] == {"firstName": ["X"]}


def test_to_payload_with_id() -> None:
    p = Person(id="Q123", firstName="X")
    assert p.to_payload()["id"] == "Q123"


def test_to_payload_omits_unset_id() -> None:
    p = Person(firstName="X")
    assert "id" not in p.to_payload()


def test_schema_literal_count() -> None:
    # 69 schemas in the bundled model — match across literals + entity classes.
    args = Schema.__args__  # type: ignore[attr-defined]
    assert len(args) == 69
    assert "Person" in args
    assert "Company" in args
    assert "Email" in args


def test_topic_literal_includes_sanction() -> None:
    args = Topic.__args__  # type: ignore[attr-defined]
    assert "sanction" in args
    assert "role.pep" in args


def test_property_type_literal() -> None:
    args = PropertyType.__args__  # type: ignore[attr-defined]
    assert "name" in args
    assert "date" in args
    assert "country" in args
    assert "entity" in args


def test_gender_literal() -> None:
    args = Gender.__args__  # type: ignore[attr-defined]
    assert set(args) == {"female", "male", "other"}
