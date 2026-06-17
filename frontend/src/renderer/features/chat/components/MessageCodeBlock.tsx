import { useEffect, useState } from "react";

import { CopyIcon } from "../../../shared/icons/LineIcons";
import { copyText } from "../clipboard";

export function MessageCodeBlock({ code, language }: { code: string; language?: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

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

  return (
    <div className="message-code-block">
      <div className="message-code-toolbar">
        <span>{language || "可复制内容"}</span>
        <button
          className={`message-code-copy ${copyState !== "idle" ? `is-${copyState}` : ""}`}
          onClick={() => void handleCopyCode()}
          title={copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制"}
          type="button"
        >
          {copyState === "copied" ? <span className="message-action-check">✓</span> : <CopyIcon />}
          {copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制"}
        </button>
      </div>
      <pre className="message-code"><code>{code}</code></pre>
    </div>
  );
}
