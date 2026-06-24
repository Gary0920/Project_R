import { useEffect, useMemo, useState } from "react";
import { useAtomValue } from "jotai";

import { authTokenAtom } from "../../auth/state";
import type { ApiClientOptions } from "../../../shared/api/client";
import { serverUrlAtom } from "../../../shared/state/server";
import { copyText } from "../clipboard";
import { inferDocumentTitle } from "../documentExport";
import { MessageDocumentLightbox } from "./MessageDocumentLightbox";
import { MessageDocumentToolbar } from "./MessageDocumentToolbar";

export function MessageDocumentBlock({ code }: { code: string }) {
  const serverUrl = useAtomValue(serverUrlAtom);
  const token = useAtomValue(authTokenAtom);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const [expanded, setExpanded] = useState(false);
  const documentTitle = useMemo(() => inferDocumentTitle(code), [code]);
  const apiOptions = useMemo<ApiClientOptions>(() => ({ baseUrl: serverUrl, token }), [serverUrl, token]);

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
    <>
      <div className="message-document-block">
        <MessageDocumentToolbar
          apiOptions={apiOptions}
          content={code}
          copyState={copyState}
          documentTitle={documentTitle}
          onCopy={() => void handleCopy()}
          onExpand={() => setExpanded(true)}
        />
        <div className="message-document-body">{code}</div>
      </div>
      {expanded ? (
        <MessageDocumentLightbox
          apiOptions={apiOptions}
          content={code}
          copyState={copyState}
          documentTitle={documentTitle}
          onClose={() => setExpanded(false)}
          onCopy={() => void handleCopy()}
        />
      ) : null}
    </>
  );
}
