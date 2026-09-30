# 004: Model routing and egress levels

## Status
Accepted for the initial build.

## Context
Rule 6: nothing leaves the node for a cloud model except through `core/egress.py`. The brief
asks that `MIA_MODEL=test` runs everything without an API key and that switching to a gateway
route needs no code change.

## Decision
- `MIA_MODEL=test` runs the agent's deterministic rules model: a Pydantic AI `FunctionModel`
  driven by the rules classifier named in the manifest (`models.classifier: rules`). It decides
  tool calls from the classified intent and writes replies only from tool results. Pydantic AI's
  `TestModel` is still used in unit tests (fixture `test_model_agent`), but it cannot hold a
  conversation, so it cannot satisfy the demo conversations. See docs/questions.md Q1.
- Any other value is a route on the Better Labs gateway: `gateway/<route>` builds
  `OpenAIChatModel(<route>)` with `OpenAIProvider(base_url=MIA_GATEWAY_URL, api_key=MIA_GATEWAY_KEY)`.
- The provider's HTTP client uses `EgressTransport`. For each request it requires an egress
  context (who, which agent, purpose, level), applies the level, writes `egress_log`, forwards,
  meters `usage_cloud_requests` from the response, and restores pseudonyms in the response.
- Levels: `none` raises `EgressBlocked` before any network call. `pseudonymised` (default)
  replaces person names, first names and inflected forms (Mikaelin becomes `Person_4:in`) with
  stable tokens (`Person_<n>` by id order); the mapping stays on the node.
  `raw_with_consent` is deferred.
- User text reaches any model only inside `<user_message>` tags, and the platform rules tell the
  model that such text is data.

## Consequences
- The pseudonymiser covers person names only. IDs, phone numbers and addresses are not replaced
  yet, and there is no general personal data filter; both are needed before real client data
  goes to a cloud model.
- No local model fallback yet: if the gateway fails, the turn fails.
