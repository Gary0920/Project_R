# GBrain Patch Records

Project_R integrates GBrain through the backend service adapter. GBrain source code should stay as close to upstream as possible.

Rules:

1. Do not silently edit `reference/gbrain-master`.
2. Prefer Project_R adapter code, GBrain config, GBrain-native skills/recipes, or better `derived/` Markdown before changing upstream source.
3. If a GBrain source change is unavoidable, record it here as a patch or move to a named Project_R fork/submodule.
4. When upgrading GBrain, re-apply these patches intentionally, resolve conflicts, and rerun GBrain sync/query regression checks.
5. If upstream GBrain adds an official config or fix that replaces a patch, remove the patch and update the ADR/docs.

Current patch set:

- `0001-ollama-local-embedding-limits.patch`: adds explicit Ollama embedding dimensions and a conservative local batch cap for `mxbai-embed-large`.
- `0002-recursive-chunker-local-ollama-cap.patch`: lowers the default Markdown chunk hard cap for local Ollama embedding stability.
- `0003-think-source-scope-gather-and-takes.patch`: threads `sourceId/allowedSources` through GBrain `think` gather, takes, and graph retrieval so source-scoped OAuth clients cannot leak cross-source evidence.
- `0004-agent-bound-oauth-client-registration.patch`: adds CLI/provider support for registering `submit_agent` OAuth clients with `bound_tools`, `bound_source_id`, `bound_slug_prefixes`, concurrency, and daily budget bindings.

These patches were recorded on 2026-05-30 after comparing Project_R's local `reference/gbrain-master` to upstream `garrytan/gbrain` commit `041d89b`.

Apply from a clean GBrain repo root:

```powershell
git apply ..\..\patches\gbrain\0001-ollama-local-embedding-limits.patch
git apply ..\..\patches\gbrain\0002-recursive-chunker-local-ollama-cap.patch
git apply ..\..\patches\gbrain\0003-think-source-scope-gather-and-takes.patch
git apply ..\..\patches\gbrain\0004-agent-bound-oauth-client-registration.patch
```
