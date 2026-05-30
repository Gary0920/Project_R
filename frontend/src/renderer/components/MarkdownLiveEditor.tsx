import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { defaultHighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorSelection, EditorState } from "@codemirror/state";
import {
  Decoration,
  type DecorationSet,
  drawSelection,
  dropCursor,
  EditorView,
  keymap,
  placeholder as editorPlaceholder,
  ViewPlugin,
  type ViewUpdate,
  WidgetType,
} from "@codemirror/view";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

export type MarkdownLiveEditorHandle = {
  applyBlockStyle: (style: MarkdownBlockStyle) => void;
  clearFormatting: () => void;
  copySelectionOrAll: () => Promise<void>;
  cutSelection: () => Promise<void>;
  formatSelection: (format: MarkdownInlineFormat) => void;
  focus: () => void;
  getBlockStyle: () => MarkdownBlockStyle;
  getValue: () => string;
  hasSelection: () => boolean;
  insertBlock: (kind: MarkdownInsertKind) => void;
  pasteFromClipboard: () => Promise<void>;
  replaceSelection: (insertText: string, selectInserted?: boolean) => void;
  selectAll: () => void;
};

export type MarkdownInlineFormat =
  | "bold"
  | "code"
  | "comment"
  | "highlight"
  | "italic"
  | "link"
  | "math"
  | "strike";

export type MarkdownBlockStyle =
  | "blockquote"
  | "bullet-list"
  | "heading-1"
  | "heading-2"
  | "heading-3"
  | "heading-4"
  | "heading-5"
  | "heading-6"
  | "numbered-list"
  | "paragraph"
  | "task-list";

export type MarkdownInsertKind = "callout" | "code-block" | "footnote" | "hr" | "math-block" | "table";

type MarkdownLiveEditorProps = {
  ariaLabel: string;
  onBlur?: () => void;
  onChange: (value: string) => void;
  placeholder: string;
  value: string;
};

const HEADING_PATTERN = /^(#{1,6})\s+/;
const TASK_PATTERN = /^(\s*)[-*]\s+\[([^\]])\]\s*/;
const CODE_FENCE_PATTERN = /^\s*```(.*)$/;

function copyTextFallback(text: string) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

async function writeClipboardText(text: string) {
  try {
    await navigator.clipboard?.writeText(text);
  } catch {
    copyTextFallback(text);
    return;
  }
  if (!navigator.clipboard) {
    copyTextFallback(text);
  }
}

class CodeCopyWidget extends WidgetType {
  constructor(private readonly code: string) {
    super();
  }

  eq(other: WidgetType) {
    return other instanceof CodeCopyWidget && other.code === this.code;
  }

  toDOM() {
    const button = document.createElement("button");
    button.className = "cm-md-code-copy-floating";
    button.type = "button";
    button.dataset.code = this.code;
    button.title = "复制代码";
    button.setAttribute("aria-label", "复制代码");
    button.textContent = "复制";
    return button;
  }

  ignoreEvent() {
    return false;
  }
}

class TaskCheckboxWidget extends WidgetType {
  constructor(
    private readonly checked: boolean,
    private readonly checkFrom: number,
  ) {
    super();
  }

  eq(other: WidgetType) {
    return other instanceof TaskCheckboxWidget
      && other.checked === this.checked
      && other.checkFrom === this.checkFrom;
  }

  toDOM() {
    const wrap = document.createElement("span");
    wrap.className = "cm-md-task-marker";
    wrap.setAttribute("aria-hidden", "true");

    const checkbox = document.createElement("input");
    checkbox.className = "cm-md-task-checkbox";
    checkbox.type = "checkbox";
    checkbox.checked = this.checked;
    checkbox.readOnly = true;
    checkbox.tabIndex = -1;
    checkbox.dataset.checkFrom = String(this.checkFrom);
    wrap.appendChild(checkbox);
    return wrap;
  }

  ignoreEvent() {
    return false;
  }
}

function selectionTouchesRange(view: EditorView, from: number, to: number) {
  return view.state.selection.ranges.some((range) => {
    if (range.empty) return range.from > from && range.from < to;
    return range.from < to && range.to > from;
  });
}

function lineHasCursor(view: EditorView, from: number, to: number) {
  return view.state.selection.ranges.some((range) => {
    if (range.empty) return range.from >= from && range.from <= to;
    return range.from <= to && range.to >= from;
  });
}

function stripBlockPrefix(text: string) {
  return text
    .replace(/^(\s*)#{1,6}\s+/, "$1")
    .replace(/^(\s*)[-*]\s+\[[ xX]\]\s+/, "$1")
    .replace(/^(\s*)[-*]\s+/, "$1")
    .replace(/^(\s*)\d+\.\s+/, "$1")
    .replace(/^(\s*)>\s?/, "$1");
}

function stripInlineMarkdown(text: string) {
  return text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/(\*\*|__)(.*?)\1/g, "$2")
    .replace(/(\*|_)(.*?)\1/g, "$2")
    .replace(/~~(.*?)~~/g, "$1")
    .replace(/==(.*?)==/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\$([^$]+)\$/g, "$1")
    .replace(/%%(.*?)%%/g, "$1");
}

function getCurrentBlockStyle(view: EditorView): MarkdownBlockStyle {
  const line = view.state.doc.lineAt(view.state.selection.main.from).text;
  const trimmed = line.trimStart();
  const headingMatch = trimmed.match(HEADING_PATTERN);
  if (headingMatch) return `heading-${Math.min(6, headingMatch[1].length)}` as MarkdownBlockStyle;
  if (/^[-*]\s+\[[ xX]\]\s+/.test(trimmed)) return "task-list";
  if (/^[-*]\s+/.test(trimmed)) return "bullet-list";
  if (/^\d+\.\s+/.test(trimmed)) return "numbered-list";
  if (/^>\s?/.test(trimmed)) return "blockquote";
  return "paragraph";
}

function buildMarkdownDecorations(view: EditorView) {
  const decorations: Array<ReturnType<Decoration["range"]>> = [];
  const { doc } = view.state;

  for (let lineNumber = 1; lineNumber <= doc.lines; lineNumber += 1) {
    const line = doc.line(lineNumber);
    const headingMatch = line.text.match(HEADING_PATTERN);
    const taskMatch = line.text.match(TASK_PATTERN);
    const codeFenceMatch = line.text.match(CODE_FENCE_PATTERN);

    if (codeFenceMatch) {
      let endLineNumber = lineNumber + 1;
      while (endLineNumber <= doc.lines && !CODE_FENCE_PATTERN.test(doc.line(endLineNumber).text)) {
        endLineNumber += 1;
      }
      const hasClosingFence = endLineNumber <= doc.lines;
      const endLine = hasClosingFence ? doc.line(endLineNumber) : doc.line(doc.lines);
      const contentFrom = line.to < doc.length ? line.to + 1 : line.to;
      const contentTo = hasClosingFence ? Math.max(contentFrom, endLine.from - 1) : endLine.to;
      const code = doc.sliceString(contentFrom, contentTo);

      decorations.push(Decoration.line({ class: "cm-md-codeblock-fence-hidden" }).range(line.from));
      if (hasClosingFence) {
        decorations.push(Decoration.line({ class: "cm-md-codeblock-fence-hidden" }).range(endLine.from));
      }

      const firstContentLine = lineNumber + 1;
      const lastContentLine = hasClosingFence ? endLineNumber - 1 : endLineNumber;
      for (let codeLineNumber = firstContentLine; codeLineNumber <= lastContentLine && codeLineNumber <= doc.lines; codeLineNumber += 1) {
        const codeLine = doc.line(codeLineNumber);
        const classes = ["cm-md-codeblock-line"];
        if (codeLineNumber === firstContentLine) classes.push("cm-md-codeblock-start");
        if (codeLineNumber === lastContentLine) classes.push("cm-md-codeblock-end");
        classes.push("cm-md-codeblock-content");
        decorations.push(Decoration.line({ class: classes.join(" ") }).range(codeLine.from));
      }
      const firstContentLineForButton = doc.line(Math.min(firstContentLine, doc.lines));
      decorations.push(
        Decoration.widget({
          side: 1,
          widget: new CodeCopyWidget(code),
        }).range(firstContentLineForButton.from),
      );

      lineNumber = hasClosingFence ? endLineNumber : doc.lines;
      continue;
    }

    if (headingMatch) {
      const level = Math.min(6, headingMatch[1].length);
      decorations.push(
        Decoration.line({ class: `cm-md-heading cm-md-heading-${level}` }).range(line.from),
      );

      const markerTo = line.from + headingMatch[0].length;
      if (!lineHasCursor(view, line.from, line.to)) {
        decorations.push(Decoration.replace({}).range(line.from, markerTo));
      }
    }

    if (taskMatch) {
      const markerFrom = line.from + taskMatch[1].length;
      const markerTo = line.from + taskMatch[0].length;
      const checkFrom = line.from + taskMatch[0].indexOf("[") + 1;
      const checked = taskMatch[2] !== " ";

      decorations.push(Decoration.line({ class: "cm-md-task-line" }).range(line.from));
      if (!selectionTouchesRange(view, markerFrom, markerTo)) {
        decorations.push(
          Decoration.replace({
            widget: new TaskCheckboxWidget(checked, checkFrom),
          }).range(markerFrom, markerTo),
        );
      }
    }
  }

  return Decoration.set(decorations, true);
}

const markdownLivePreview = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;

    constructor(view: EditorView) {
      this.decorations = buildMarkdownDecorations(view);
    }

    update(update: ViewUpdate) {
      if (update.docChanged || update.selectionSet || update.viewportChanged) {
        this.decorations = buildMarkdownDecorations(update.view);
      }
    }
  },
  {
    decorations: (plugin) => plugin.decorations,
    eventHandlers: {
      mousedown: (event, view) => {
        const target = event.target as HTMLElement | null;
        const copyButton = target?.closest<HTMLButtonElement>("button.cm-md-code-copy-floating");
        if (copyButton) {
          void writeClipboardText(copyButton.dataset.code ?? "");
          copyButton.textContent = "已复制";
          window.setTimeout(() => {
            copyButton.textContent = "复制";
          }, 900);
          event.preventDefault();
          return true;
        }

        const checkbox = target?.closest<HTMLInputElement>("input.cm-md-task-checkbox");
        if (!checkbox) return false;

        const checkFrom = Number(checkbox.dataset.checkFrom);
        if (!Number.isFinite(checkFrom)) return false;

        const current = view.state.doc.sliceString(checkFrom, checkFrom + 1);
        view.dispatch({
          changes: { from: checkFrom, to: checkFrom + 1, insert: current === " " ? "x" : " " },
          selection: { anchor: checkFrom + 1 },
          scrollIntoView: true,
        });
        view.focus();
        event.preventDefault();
        return true;
      },
    },
  },
);

export const MarkdownLiveEditor = forwardRef<MarkdownLiveEditorHandle, MarkdownLiveEditorProps>(
  function MarkdownLiveEditor({ ariaLabel, onBlur, onChange, placeholder, value }, ref) {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const viewRef = useRef<EditorView | null>(null);
    const onBlurRef = useRef(onBlur);
    const onChangeRef = useRef(onChange);

    useEffect(() => {
      onBlurRef.current = onBlur;
      onChangeRef.current = onChange;
    }, [onBlur, onChange]);

    useEffect(() => {
      const container = containerRef.current;
      if (!container) return;

      const view = new EditorView({
        parent: container,
        state: EditorState.create({
          doc: value,
          extensions: [
            history(),
            drawSelection(),
            dropCursor(),
            markdown(),
            syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
            editorPlaceholder(placeholder),
            markdownLivePreview,
            EditorView.lineWrapping,
            EditorView.contentAttributes.of({
              "aria-label": ariaLabel,
              spellcheck: "false",
            }),
            EditorView.updateListener.of((update) => {
              if (update.docChanged) {
                onChangeRef.current(update.state.doc.toString());
              }
            }),
            EditorView.domEventHandlers({
              blur: () => {
                onBlurRef.current?.();
                return false;
              },
            }),
            keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
          ],
        }),
      });

      viewRef.current = view;
      return () => {
        view.destroy();
        viewRef.current = null;
      };
    }, []);

    useEffect(() => {
      const view = viewRef.current;
      if (!view) return;
      const current = view.state.doc.toString();
      if (current === value) return;
      view.dispatch({
        changes: { from: 0, to: current.length, insert: value },
      });
    }, [value]);

    useImperativeHandle(ref, () => ({
      applyBlockStyle(style) {
        const view = viewRef.current;
        if (!view) return;

        const selection = view.state.selection.main;
        const startLine = view.state.doc.lineAt(selection.from);
        const endLine = view.state.doc.lineAt(selection.to);
        const changes = [];
        let itemIndex = 1;

        for (let lineNumber = startLine.number; lineNumber <= endLine.number; lineNumber += 1) {
          const line = view.state.doc.line(lineNumber);
          const cleanText = stripBlockPrefix(line.text);
          const content = cleanText.trim() ? cleanText : "";
          let nextText = cleanText;

          if (style.startsWith("heading-")) {
            const level = Number(style.replace("heading-", ""));
            nextText = `${"#".repeat(Math.min(6, Math.max(1, level)))} ${content || "标题"}`;
          } else if (style === "bullet-list") {
            nextText = `- ${content || "列表项"}`;
          } else if (style === "numbered-list") {
            nextText = `${itemIndex}. ${content || "列表项"}`;
            itemIndex += 1;
          } else if (style === "task-list") {
            nextText = `- [ ] ${content || "待办事项"}`;
          } else if (style === "blockquote") {
            nextText = `> ${content || "引用"}`;
          } else {
            nextText = content;
          }

          changes.push({ from: line.from, to: line.to, insert: nextText });
        }

        view.dispatch({ changes, scrollIntoView: true });
        view.focus();
      },
      clearFormatting() {
        const view = viewRef.current;
        if (!view) return;
        const selection = view.state.selection.main;

        if (!selection.empty) {
          const selectedText = view.state.doc.sliceString(selection.from, selection.to);
          const cleanText = stripInlineMarkdown(selectedText);
          view.dispatch({
            changes: { from: selection.from, to: selection.to, insert: cleanText },
            selection: EditorSelection.range(selection.from, selection.from + cleanText.length),
            scrollIntoView: true,
          });
          view.focus();
          return;
        }

        const line = view.state.doc.lineAt(selection.from);
        const cleanText = stripInlineMarkdown(stripBlockPrefix(line.text));
        view.dispatch({
          changes: { from: line.from, to: line.to, insert: cleanText },
          selection: EditorSelection.cursor(line.from + cleanText.length),
          scrollIntoView: true,
        });
        view.focus();
      },
      async copySelectionOrAll() {
        const view = viewRef.current;
        if (!view) return;
        const ranges = view.state.selection.ranges.filter((range) => !range.empty);
        const text = ranges.length
          ? ranges.map((range) => view.state.doc.sliceString(range.from, range.to)).join("\n")
          : view.state.doc.toString();
        if (text) await navigator.clipboard?.writeText(text);
      },
      async cutSelection() {
        const view = viewRef.current;
        if (!view) return;
        const selection = view.state.selection.main;
        if (selection.empty) return;
        const text = view.state.doc.sliceString(selection.from, selection.to);
        await navigator.clipboard?.writeText(text);
        view.dispatch({
          changes: { from: selection.from, to: selection.to, insert: "" },
          selection: EditorSelection.cursor(selection.from),
          scrollIntoView: true,
        });
        view.focus();
      },
      formatSelection(format) {
        const view = viewRef.current;
        if (!view) return;
        const selection = view.state.selection.main;
        const selectedText = selection.empty
          ? format === "link" ? "链接文本" : "文本"
          : view.state.doc.sliceString(selection.from, selection.to);
        let insertText = selectedText;
        let innerFromOffset = 0;
        let innerToOffset = selectedText.length;

        if (format === "link") {
          const href = window.prompt("请输入链接地址", "https://");
          if (!href) return;
          insertText = `[${selectedText}](${href})`;
          innerFromOffset = 1;
          innerToOffset = 1 + selectedText.length;
        } else if (format === "bold") {
          insertText = `**${selectedText}**`;
          innerFromOffset = 2;
          innerToOffset = 2 + selectedText.length;
        } else if (format === "italic") {
          insertText = `*${selectedText}*`;
          innerFromOffset = 1;
          innerToOffset = 1 + selectedText.length;
        } else if (format === "strike") {
          insertText = `~~${selectedText}~~`;
          innerFromOffset = 2;
          innerToOffset = 2 + selectedText.length;
        } else if (format === "highlight") {
          insertText = `==${selectedText}==`;
          innerFromOffset = 2;
          innerToOffset = 2 + selectedText.length;
        } else if (format === "code") {
          insertText = `\`${selectedText}\``;
          innerFromOffset = 1;
          innerToOffset = 1 + selectedText.length;
        } else if (format === "math") {
          insertText = `$${selectedText}$`;
          innerFromOffset = 1;
          innerToOffset = 1 + selectedText.length;
        } else if (format === "comment") {
          insertText = `%%${selectedText}%%`;
          innerFromOffset = 2;
          innerToOffset = 2 + selectedText.length;
        }

        view.dispatch({
          changes: { from: selection.from, to: selection.to, insert: insertText },
          selection: selection.empty
            ? EditorSelection.range(selection.from + innerFromOffset, selection.from + innerToOffset)
            : EditorSelection.cursor(selection.from + insertText.length),
          scrollIntoView: true,
        });
        view.focus();
      },
      focus() {
        viewRef.current?.focus();
      },
      getBlockStyle() {
        const view = viewRef.current;
        return view ? getCurrentBlockStyle(view) : "paragraph";
      },
      getValue() {
        return viewRef.current?.state.doc.toString() ?? "";
      },
      hasSelection() {
        const view = viewRef.current;
        return Boolean(view && !view.state.selection.main.empty);
      },
      insertBlock(kind) {
        if (kind === "footnote") {
          this.replaceSelection("[^1]\n\n[^1]: 脚注内容\n", true);
        } else if (kind === "table") {
          this.replaceSelection("| 列 1 | 列 2 |\n| --- | --- |\n| 内容 | 内容 |\n", true);
        } else if (kind === "callout") {
          this.replaceSelection("> [!note]\n> 标注内容\n", true);
        } else if (kind === "hr") {
          this.replaceSelection("---\n", false);
        } else if (kind === "code-block") {
          const view = viewRef.current;
          if (!view) return;
          const selection = view.state.selection.main;
          const before = selection.from > 0
            ? view.state.doc.sliceString(selection.from - 1, selection.from)
            : "";
          const needsLeadingBreak = selection.from > 0 && before !== "\n" ? "\n" : "";
          const insertText = `${needsLeadingBreak}\`\`\`text\n\n\`\`\`\n`;
          const cursor = selection.from + needsLeadingBreak.length + "```text\n".length;
          view.dispatch({
            changes: { from: selection.from, to: selection.to, insert: insertText },
            selection: EditorSelection.cursor(cursor),
            scrollIntoView: true,
          });
          view.focus();
        } else if (kind === "math-block") {
          this.replaceSelection("$$\n\n$$\n", true);
        }
      },
      async pasteFromClipboard() {
        const text = await navigator.clipboard?.readText();
        if (text) this.replaceSelection(text);
      },
      replaceSelection(insertText: string, selectInserted = false) {
        const view = viewRef.current;
        if (!view) return;

        const selection = view.state.selection.main;
        const before = selection.from > 0
          ? view.state.doc.sliceString(selection.from - 1, selection.from)
          : "";
        const needsLeadingBreak = selection.from > 0 && before !== "\n" ? "\n" : "";
        const nextInsert = `${needsLeadingBreak}${insertText}`;
        const insertedStart = selection.from + needsLeadingBreak.length;
        const insertedEnd = insertedStart + insertText.length;

        view.dispatch({
          changes: { from: selection.from, to: selection.to, insert: nextInsert },
          selection: selectInserted
            ? EditorSelection.range(insertedStart, insertedEnd)
            : EditorSelection.cursor(insertedEnd),
          scrollIntoView: true,
        });
        view.focus();
      },
      selectAll() {
        const view = viewRef.current;
        if (!view) return;
        view.dispatch({
          selection: EditorSelection.single(0, view.state.doc.length),
          scrollIntoView: true,
        });
        view.focus();
      },
    }));

    return <div className="markdown-live-editor" ref={containerRef} />;
  },
);
