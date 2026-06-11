import { useAtom, useSetAtom } from "jotai";
import { useEffect, useRef, useState } from "react";

import { apiRequest } from "../shared/api/client";
import type { HealthResponse } from "../shared/api/types";
import { serverUrlAtom, setServerUrlAtom } from "../shared/state/server";
import { APP_NAME, DEFAULT_API_BASE_URL } from "../shared/config/app";

type CheckState = "idle" | "checking" | "ok" | "error";

export function OnboardingPage({ onComplete }: { onComplete: () => void }) {
  const [serverUrl] = useAtom(serverUrlAtom);
  const setServerUrl = useSetAtom(setServerUrlAtom);
  const [draftUrl, setDraftUrl] = useState(serverUrl || DEFAULT_API_BASE_URL);
  const [checkState, setCheckState] = useState<CheckState>("idle");
  const [message, setMessage] = useState("");
  const mountedRef = useRef(false);

  useEffect(() => {
    if (mountedRef.current) return;
    mountedRef.current = true;
    void checkServer(serverUrl || DEFAULT_API_BASE_URL);
  }, [serverUrl]);

  async function checkServer(target = draftUrl) {
    const normalized = target.trim().replace(/\/$/, "");
    if (!normalized) {
      setCheckState("error");
      setMessage("请填写后端地址");
      return false;
    }
    setCheckState("checking");
    setMessage("正在连接后端服务");
    try {
      const health = await apiRequest<HealthResponse>({ baseUrl: normalized }, "/health");
      if (health.status === "ok") {
        setCheckState("ok");
        setMessage("后端连接正常");
        setServerUrl(normalized);
        return true;
      }
      setCheckState("error");
      setMessage(`后端返回异常：${health.status}`);
      return false;
    } catch {
      setCheckState("error");
      setMessage("连接失败，请检查地址或后端是否启动");
      return false;
    }
  }

  return (
    <div className="gate-page">
      <div className="gate-ambient" aria-hidden="true">
        <div className="aurora-blob blob-1" />
        <div className="aurora-blob blob-2" />
        <div className="aurora-blob blob-3" />
      </div>

      <main className="gate-content">
        <div className="gate-brand">
          <div className="gate-mark">R</div>
          <h1 className="gate-title">{APP_NAME}</h1>
          <p className="gate-lead">公司内部 AI 智能办公辅助系统</p>
        </div>

        <div className="gate-divider" />

        <div className={`gate-status ${checkState}`}>
          <div className="gate-pulse">
            {checkState === "ok" ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : checkState === "error" ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            ) : (
              <span className="gate-dot" />
            )}
          </div>
          <p className="gate-status-text">{message || "等待检测"}</p>
        </div>

        <div className="gate-form">
          <label className="gate-input-line">
            <span>后端地址</span>
            <input
              type="text"
              value={draftUrl}
              onChange={(event) => {
                setDraftUrl(event.target.value);
                if (checkState !== "idle") {
                  setCheckState("idle");
                  setMessage("");
                }
              }}
              placeholder={DEFAULT_API_BASE_URL}
            />
          </label>

          <div className="gate-buttons">
            <button
              className="gate-btn"
              disabled={checkState === "checking"}
              onClick={() => void checkServer()}
              type="button"
            >
              {checkState === "checking" ? "检测中…" : "重新检测"}
            </button>
            <button
              className="gate-btn gate-btn-accent"
              disabled={checkState !== "ok"}
              onClick={onComplete}
              type="button"
            >
              进入登录
            </button>
          </div>
        </div>

        <footer className="gate-foot">
          <span>检测通过后方可进入系统</span>
          <span className="gate-foot-sep" />
          <span>地址仅保存在本地</span>
        </footer>
      </main>
    </div>
  );
}
