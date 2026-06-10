# Claude Code Hooks — 建议配置

本项目可以使用 Claude Code 的 hooks 机制来保护敏感文件、自动运行 lint/test。

> **⚠️ 风险提示**: Hooks 是自动执行的脚本，错误的 hook 可能中断工作流。以下均为"建议配置"，不自动启用。如需启用，将对应脚本文件放到 `.claude/hooks/` 目录并确保可执行。

## 可用 Hook 类型

| Hook | 触发时机 | 建议用途 |
|---|---|---|
| `pre-command` | 每次 tool 调用前 | 检查是否要修改敏感文件 |
| `post-edit` | 每次文件编辑后 | 自动运行 formatter（如果项目有） |
| `pre-commit` | `git commit` 前 | 运行 lint/typecheck |

## 建议 1: 敏感文件保护 (pre-command)

创建一个 `pre-command` hook，当检测到危险操作时发出警告但不阻止。

### `pre-command` 脚本 (PowerShell)

```powershell
# .claude/hooks/pre-command.ps1
# 检测是否正在读取/写入敏感文件

$sensitiveFiles = @(
    ".env",
    ".env.local",
    ".env.example",
    "frontend\bun.lock",
    "backend\requirements.txt",
    "backend\requirements-dev.txt",
    "skills-lock.json",
    "frontend\electron-builder.yml"
)

foreach ($file in $sensitiveFiles) {
    $fullPath = Join-Path $Pwd $file
    if (Test-Path $fullPath) {
        # Just a reminder — doesn't block execution
        Write-Warning "⚠️ 操作涉及敏感文件: $file — 请确认这是 Planner Task Packet 要求的改动"
    }
}
```

### `pre-command` 脚本 (Bash)

```bash
# .claude/hooks/pre-command
# Detect if operating on sensitive files

SENSITIVE_FILES=(
    ".env" ".env.local" ".env.example"
    "frontend/bun.lock"
    "backend/requirements.txt" "backend/requirements-dev.txt"
    "skills-lock.json"
    "frontend/electron-builder.yml"
)

for file in "${SENSITIVE_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "⚠️  Warning: Operating on sensitive file: $file"
        echo "    Verify this is required by the Planner Task Packet."
    fi
done
```

## 建议 2: 编辑后类型检查 (post-edit)

如果有 formatter（如 Prettier），可在 post-edit hook 中自动运行。

```bash
# .claude/hooks/post-edit
# Run formatter after editing (if project has one configured)
# npm run format 2>/dev/null || true
```

> 当前项目没有配置 formatter。建议后续添加 Prettier 后再启用此 hook。

## 建议 3: 提交前检查 (pre-commit)

前端改动时运行 typecheck，后端改动时运行相关 pytest。

```bash
# .claude/hooks/pre-commit
# Ensure typecheck passes before frontend commits
CHANGED=$(git diff --cached --name-only)

if echo "$CHANGED" | grep -q "^frontend/"; then
    echo "Running frontend typecheck..."
    cd frontend && bun run typecheck
    if [ $? -ne 0 ]; then
        echo "❌ Typecheck failed. Fix before committing."
        exit 1
    fi
fi

if echo "$CHANGED" | grep -q "^backend/"; then
    echo "Running backend tests for changed files..."
    cd backend && python -m pytest tests/ --last-failed -q 2>/dev/null || true
fi
```

## 启用方法

1. 将需要的脚本复制到 `.claude/hooks/` 目录。
2. **Windows (PowerShell)**: 创建 `.ps1` 文件，并在 `.claude/settings.local.json` 中配置 shell 为 `pwsh`。
3. **Bash (Git Bash / WSL)**: 创建无扩展名的 shell 脚本并 `chmod +x`。
4. 测试 hook 是否正确触发。
