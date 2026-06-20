# GBrain 0.42.51 Rebased Patch Set

Generated for `reference/gbrain-upstream-0.42.51` on the Project_R rebase branch.

## Upstream Baseline

| Item | Value |
|---|---|
| `VERSION` | `0.42.51.0` |
| `HEAD` | `9bf96db807c2f050449142f2f0b05726f58e5054` |
| Rebase branch | `project-r-0.42.51-rebased` |

## Patch Status

| Patch | Status | Artifact | Notes |
|---|---|---|---|
| `0001` | `rebased` | `0001-ollama-local-embedding-limits.patch` | Keeps conservative Ollama local embedding limits. |
| `0002` | `rebased` | `0002-recursive-chunker-local-ollama-cap.patch` | Keeps local-Ollama-safe recursive chunk cap. |
| `0003` | `rebased` | `0003-think-source-scope-gather-and-takes.patch` | Threads scalar and federated source scope through think gather, takes retrieval, and tests. This file also contains the overlapping `gather.ts` hunk where `0007` is folded into the current branch state. |
| `0004` | `rebased` | `0004-agent-bound-oauth-client-registration.patch` | Adds manual/CLI agent-bound OAuth client registration flags and tests. |
| `0005` | `rebased` | `0005-subagent-tool-source-scope.patch` | Makes subagent brain tools inherit bound source scope and adds regression coverage. |
| `0006` | `absorbed_by_upstream` | none | Upstream already wraps tool schemas with `jsonSchema()` and converts tool-result messages for AI SDK v6. Keep `test/ai/gateway-tool-loop.test.ts` in validation. |
| `0007` | `rebased_logical_overlap` | `0007-think-gather-title-query-variants.logical.patch` | The title-query implementation overlaps the same `src/core/think/gather.ts` stream-1 hunk as `0003`. Use this file as a logical review artifact; apply the branch diff or `0003` artifact for the concrete combined hunk. |
| `0008` | `rebased` | `0008-doctor-resolver-health-windows-crlf.patch` | Fixes resolver health on Windows by making skill frontmatter trigger parsing CRLF-safe, reusing the shared parser, adding the missing `skill-optimizer` resolver row, and making path-suffix tests separator-agnostic. |
| `0009` | `rebased` | `0009-windows-source-run-apply-migrations.patch` | Fixes Windows/source-run `apply-migrations` by reusing the current CLI invocation instead of assuming a globally installed `gbrain` command; adds regression coverage for v0.11-v0.13 migration subprocesses. |

## Apply Notes

- Prefer the maintained rebase branch as the source of truth for this patch set.
- `0001`, `0002`, `0004`, and `0005` are path-isolated patch artifacts.
- `0003` and `0007` both edit `src/core/think/gather.ts`; applying them as independent unordered patches is unsafe.
- `0006` must not be re-applied to `0.42.51`; validation should keep the gateway-loop regression test.
- `0008` is required before formal cutover on Windows; without it, `doctor --fast --json` can report resolver/skill hygiene as unhealthy even when bundled skill frontmatter already contains triggers.
- `0009` is required for source-run Windows installs where `gbrain` is not on PATH; without it, `apply-migrations` can fail inside v0.11-v0.13 orchestrators despite `bun run src/cli.ts ...` working.

## Validation Targets

Run from `reference/gbrain-upstream-0.42.51`:

```powershell
bun run typecheck
bun test test/check-resolvable.test.ts test/check-resolvable-cli.test.ts test/doctor-behavioral.test.ts test/brain-score-breakdown.test.ts
bun test test/auth-register-client-args.test.ts test/oauth.test.ts test/brain-allowlist.serial.test.ts test/takes-engine.test.ts test/think-pipeline.serial.test.ts test/ai/gateway-tool-loop.test.ts test/fix-wave-structural.test.ts
bun run build
```
