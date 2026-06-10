# Return Report

## Description
Compile and format the result of the current Executor task into the required return format. Use this after completing implementation and validation.

## Usage
```
/return-report
```

This command gathers the context of the current task and outputs a structured report. It does not modify any files.

## Report Format

```markdown
## Summary of Changes
Brief description of what was implemented and why.

## Files Changed
- [path/to/file] — created/modified/deleted, with one-line purpose

## Validation Results
- Command: `exact command run`
- Output: (key output lines)
- Result: ✅ Passed / ❌ Failed / ⚠️ Partial

## Deviations from Plan
- (Any deviation, with justification)
- If none: "None"

## Open Questions or Blockers
- (Any items needing Planner attention)
- If none: "None"
```

## Notes
- Run validation commands before calling this command.
- If validation failed, include the failure details and your diagnosis.
- Be honest about deviations — the Planner needs accurate information to decide next steps.
