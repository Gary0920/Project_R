# Execute Task

## Description
Execute a Planner-provided Executor Task Packet. Use this when an external Planner (e.g. Codex GPT-5.5) has given you a structured task definition.

## Usage
```
/execute-task
```

Then paste the full Executor Task Packet from the Planner. The command will:
1. First restate the Objective, Scope, and Out Of Scope for confirmation.
2. Read the specified files to inspect first.
3. Implement the changes strictly within scope.
4. Run the required validation commands.
5. Return a structured report.

## Execution Protocol

1. **Confirm understanding**: Restate objective, scope, and out-of-scope boundaries.
2. **Inspect**: Read each file listed in `Files To Inspect First`.
3. **Implement**: Make only in-scope changes. Follow existing project style.
4. **Validate**: Run all validation commands listed in the packet.
5. **Report**: Use the `Return Format` from the packet. If none specified, use the format from CLAUDE.md `## Executor 角色规则 → 输出要求`.

## Important Constraints
- Do not change architecture, add dependencies, modify public interfaces, delete behavior, or expand scope.
- If blocked (unclear requirements, failing tests with unknown cause, scope conflict), stop and ask.
- Report all deviations from the plan in the final report.
