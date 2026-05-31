# Response models

Pydantic models returned by the client methods. All set
`extra="ignore"` — unknown server-side fields are silently dropped so
the client doesn't break when yente adds a field.

::: yente_client.models
