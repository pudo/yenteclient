# Entities

Per-schema input classes used to construct `match()` queries. One class per
FtM schema (`Person`, `Company`, `Vessel`, `Organization`, `LegalEntity`, …).

Use [`yente-cli ref schemas`](../cli.md) to discover the full set, and
[`yente-cli ref schema NAME`](../cli.md) to see which properties each
schema accepts.

## EntityInput

::: yente_client.entities.EntityInput

## Representative schemas

The classes themselves carry their FtM properties as Pydantic fields
(camelCase, matching the wire format). See `ref schema NAME` for the
full property list per schema.

::: yente_client.entities.Person
    options:
      members: false
      show_bases: true

::: yente_client.entities.Company
    options:
      members: false
      show_bases: true

::: yente_client.entities.Organization
    options:
      members: false
      show_bases: true

::: yente_client.entities.LegalEntity
    options:
      members: false
      show_bases: true

::: yente_client.entities.Vessel
    options:
      members: false
      show_bases: true
