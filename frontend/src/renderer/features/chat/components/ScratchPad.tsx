import { useEffect, useRef, useState, type MouseEvent } from "react";

import { useContextMenu, type ContextMenuItemDef } from "../../../shared/components/ContextMenu";
import {
  MarkdownLiveEditor,
  type MarkdownBlockStyle,
  type MarkdownLiveEditorHandle,
} from "../../../shared/components/MarkdownLiveEditor";

const STORAGE_PREFIX = "project-r:scratch-content";

function makeStorageKey(userId: number | null | undefined, workspaceId: number | null | undefined) {
  return `${STORAGE_PREFIX}:${userId ?? "anonymous"}:${workspaceId ?? "no-project"}`;
}

function loadContent(storageKey: string): string {
  try {
    return localStorage.getItem(storageKey) ?? "";
  } catch {
    return "";
  }
}

function saveContent(storageKey: string, content: string) {
  try {
    localStorage.setItem(storageKey, content);
  } catch {
    // ignore
  }
}

export function ScratchPad({
  workspaceId,
  workspaceName,
  userId,
  onClose,
}: {
  workspaceId: number | null;
  workspaceName?: string;
  userId?: number | null;
  onClose?: () => void;
}) {
  const storageKey = makeStorageKey(userId, workspaceId);
  const [content, setContent] = useState(() => loadContent(storageKey));
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; items: ContextMenuItemDef[] } | null>(null);
  const editorRef = useRef<MarkdownLiveEditorHandle | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  useEffect(() => {
    setContent(loadContent(storageKey));
  }, [storageKey]);

  function handleChange(value: string) {
    setContent(value);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => saveContent(storageKey, value), 500);
  }

  function updateContent(nextContent: string) {
    setContent(nextContent);
    saveContent(storageKey, nextContent);
  }

  // Persist on unmount
  useEffect(() => {
    return () => saveContent(storageKey, content);
  }, [content, storageKey]);

  function handleExport() {
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `notes-${new Date().toISOString().slice(0, 10)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function clearNote() {
    if (!content.trim() || window.confirm("确定清空当前个人笔记吗？")) {
      updateContent("");
      window.requestAnimationFrame(() => editorRef.current?.focus());
    }
  }

  function openScratchContextMenu(event: MouseEvent) {
    event.preventDefault();
    editorRef.current?.focus();
    const editor = editorRef.current;
    const hasSelection = Boolean(editor?.hasSelection());
    const currentBlock = editor?.getBlockStyle() ?? "paragraph";
    const blockItem = (label: string, style: MarkdownBlockStyle): ContextMenuItemDef => ({
      type: "item",
      label,
      checked: currentBlock === style,
      action: () => editor?.applyBlockStyle(style),
    });

    const items: ContextMenuItemDef[] = [
      { type: "item", label: "新增外部链接", action: () => editor?.formatSelection("link") },
      { type: "separator" },
      {
        type: "item",
        label: "文本格式",
        children: [
          { type: "item", label: "加粗", action: () => editor?.formatSelection("bold") },
          { type: "item", label: "倾斜", action: () => editor?.formatSelection("italic") },
          { type: "item", label: "删除线", action: () => editor?.formatSelection("strike") },
          { type: "item", label: "高亮", action: () => editor?.formatSelection("highlight") },
          { type: "separator" },
          { type: "item", label: "代码", action: () => editor?.formatSelection("code") },
          { type: "item", label: "数学", action: () => editor?.formatSelection("math") },
          { type: "item", label: "注释", action: () => editor?.formatSelection("comment") },
          { type: "separator" },
          { type: "item", label: "清除格式", action: () => editor?.clearFormatting() },
        ],
      },
      {
        type: "item",
        label: "段落设置",
        children: [
          blockItem("无序列表", "bullet-list"),
          blockItem("有序列表", "numbered-list"),
          blockItem("任务列表", "task-list"),
          { type: "separator" },
          blockItem("1级标题", "heading-1"),
          blockItem("2级标题", "heading-2"),
          blockItem("3级标题", "heading-3"),
          blockItem("4级标题", "heading-4"),
          blockItem("5级标题", "heading-5"),
          blockItem("6级标题", "heading-6"),
          blockItem("正文", "paragraph"),
          { type: "separator" },
          blockItem("引用", "blockquote"),
        ],
      },
      {
        type: "item",
        label: "插入",
        children: [
          { type: "item", label: "脚注", action: () => editor?.insertBlock("footnote") },
          { type: "item", label: "表格", action: () => editor?.insertBlock("table") },
          { type: "item", label: "标注", action: () => editor?.insertBlock("callout") },
          { type: "item", label: "分隔线", action: () => editor?.insertBlock("hr") },
          { type: "separator" },
          { type: "item", label: "代码块", action: () => editor?.insertBlock("code-block") },
          { type: "item", label: "数学块", action: () => editor?.insertBlock("math-block") },
        ],
      },
      { type: "separator" },
      { type: "item", label: "剪切", disabled: !hasSelection, action: () => void editor?.cutSelection() },
      { type: "item", label: "复制", disabled: !hasSelection, action: () => void editor?.copySelectionOrAll() },
      { type: "item", label: "粘贴", action: () => void editor?.pasteFromClipboard() },
      { type: "item", label: "以纯文本形式粘贴", action: () => void editor?.pasteFromClipboard() },
      { type: "item", label: "全选", action: () => editor?.selectAll() },
      { type: "separator" },
      { type: "item", label: "导出 Markdown", action: handleExport },
      { type: "item", label: "清空笔记", destructive: true, action: clearNote },
    ];
    setContextMenu({ x: event.clientX, y: event.clientY, items });
  }

  return (
    <div className="scratch-pad" onContextMenu={openScratchContextMenu}>
      <div className="scratch-pad-project">
        <div>
          <strong>{workspaceName ?? "未选择项目"}</strong>
          <span>本地个人笔记，仅当前用户可见</span>
        </div>
        {onClose ? (
          <button className="scratch-pad-close" onClick={onClose} title="关闭快速笔记" type="button">
            ×
          </button>
        ) : null}
      </div>
      <section className="scratch-pad-live-panel">
        <MarkdownLiveEditor
          ariaLabel="个人 Markdown 笔记"
          onBlur={() => saveContent(storageKey, editorRef.current?.getValue() ?? content)}
          onChange={handleChange}
          placeholder={"# 今日笔记\n\n- [ ] 待办事项\n- [x] 已完成事项\n\n```text\n临时资料\n```"}
          ref={editorRef}
          value={content}
        />
      </section>
      <div className="scratch-pad-toolbar">
        <span className="scratch-pad-hint">内容自动保存到本地</span>
        <button className="scratch-pad-export-btn" onClick={handleExport} type="button">
          导出 Markdown
        </button>
      </div>
      {useContextMenu(contextMenu, setContextMenu)}
    </div>
  );
}
