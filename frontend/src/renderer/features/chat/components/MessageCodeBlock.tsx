import { useEffect, useState } from "react";

import { CheckIcon, CopyIcon, DownloadIcon, EditIcon, MaximizeIcon, XmarkIcon } from "../../../shared/icons/LineIcons";
import { copyText } from "../clipboard";

export function MessageCodeBlock({ code, language }: { code: string; language?: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const [fullscreenOpen, setFullscreenOpen] = useState(false);

  useEffect(() => {
    if (copyState === "idle") return;
    const timer = window.setTimeout(() => setCopyState("idle"), 1600);
    return () => window.clearTimeout(timer);
  }, [copyState]);

  async function handleCopyCode() {
    try {
      await copyText(code);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  function handleDownloadCode() {
    const extension = language?.toLowerCase() || "txt";
    const fileName = `project-r-code-${Date.now()}.${extension === "markdown" ? "md" : extension}`;
    const blob = new Blob([code], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <div className="message-code-block">
        <div className="message-code-toolbar">
          <div className="message-code-toolbar-left">
            <button
              aria-label="暂未接入编辑"
              className="message-code-edit-btn"
              disabled
              title="暂未接入编辑"
              type="button"
            >
              <EditIcon />
              <span>编辑</span>
            </button>
            <span className="message-code-label">{language || "可复制内容"}</span>
          </div>
          <div className="message-code-actions" aria-label="代码块操作">
            <button
              aria-label={copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制代码"}
              className={`message-code-tool-btn ${copyState !== "idle" ? `is-${copyState}` : ""}`}
              onClick={() => void handleCopyCode()}
              title={copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制代码"}
              type="button"
            >
              {copyState === "copied" ? <CheckIcon /> : <CopyIcon />}
            </button>
            <button
              aria-label="下载代码"
              className="message-code-tool-btn"
              onClick={handleDownloadCode}
              title="下载代码"
              type="button"
            >
              <DownloadIcon />
            </button>
            <button
              aria-label="全屏阅读"
              className="message-code-tool-btn"
              onClick={() => setFullscreenOpen(true)}
              title="全屏阅读"
              type="button"
            >
              <MaximizeIcon />
            </button>
          </div>
        </div>
        <pre className="message-code"><code>{code}</code></pre>
      </div>
      {fullscreenOpen ? (
        <div className="message-code-fullscreen-backdrop" onClick={() => setFullscreenOpen(false)} role="presentation">
          <section
            aria-label="代码全屏阅读"
            className="message-code-fullscreen"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="message-code-fullscreen-header">
              <span>{language || "可复制内容"}</span>
              <button
                aria-label="关闭"
                className="message-code-tool-btn"
                onClick={() => setFullscreenOpen(false)}
                type="button"
              >
                <XmarkIcon />
              </button>
            </div>
            <pre className="message-code message-code-fullscreen-body"><code>{code}</code></pre>
          </section>
        </div>
      ) : null}
    </>
  );
}
