import { useEffect, useState } from "react";

import { CopyIcon } from "../../../shared/icons/LineIcons";
import { copyText } from "../clipboard";

export function MessageDocumentBlock({ code }: { code: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (copyState === "idle") return;
    const timer = window.setTimeout(() => setCopyState("idle"), 1600);
    return () => window.clearTimeout(timer);
  }, [copyState]);

  async function handleCopy() {
    try {
      await copyText(code);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  return (
    <div className="message-document-block">
      <div className="message-document-toolbar">
        <button
          className={`ghost-button message-document-copy ${copyState !== "idle" ? `is-${copyState}` : ""}`}
          onClick={() => void handleCopy()}
          type="button"
        >
          <CopyIcon />
          {copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制"}
        </button>
      </div>
      <div className="message-document-body">{code}</div>
    </div>
  );
}
