# Get started with the yente-client Python SDK

A linear tour: install → first match → matching in depth → fetch →
search → async → errors → entities → next steps. If you want shell
access rather than Python, see [CLI overview](cli.md) instead.

## 1. Install and authenticate

_(stub — to be written in step 3.)_

## 2. Your first match

_(stub.)_

### Construct an entity

### Run the match

### Read the response

## 3. Matching in depth

_(stub.)_

### The threshold

### Choosing an algorithm

### Narrowing with MatchFilters

### One HTTP call per match

## 4. Fetch and adjacency

_(stub.)_

### Fetch by ID

### Nested vs flat

### Adjacent entities and paging

## 5. Search (for user-facing search UIs)

_(stub. Search is a different use case from matching — autocomplete,
browse, search boxes. Any matching task uses `match` even with partial
input.)_

### When to use search vs match

### A search example

### Filters and facets

## 6. Async

_(stub.)_

### AsyncClient lifecycle

### Concurrent matches with asyncio.gather

## 7. Errors

_(stub.)_

### The exception tree

### Catching by category vs by type

### Input-shape errors (pydantic)

## 8. Entities and the FtM model

_(stub. Per-schema input classes, the bundled snapshot, discovery via
`yente-cli ref`. Covers schema-level matchable and the "directly
scored" vs "useful in matching" distinction for properties.)_

### Per-schema input classes

### The bundled model snapshot

### Discovering schemas with `yente-cli ref`

### Matchable schemata and the property `directly_scored` flag

## 9. Where to go next

- [CLI overview](cli.md) for shell access and agent automations.
- [API reference](api/index.md) for full signatures of every public
  symbol.
- [OpenSanctions docs](https://www.opensanctions.org/docs/) for
  product / domain context (sanctions screening, FtM model, hosted-API
  quickstart, getting an API key).
