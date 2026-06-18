import { useAtom, useSetAtom } from "jotai";
import { useEffect, useRef, useState } from "react";

import { apiRequest } from "../shared/api/client";
import type { HealthResponse } from "../shared/api/types";
import { serverUrlAtom, setServerUrlAtom } from "../shared/state/server";
import { APP_NAME, DEFAULT_API_BASE_URL } from "../shared/config/app";
import ravenLogo from "../shared/assets/raven-logo.png";

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
    setMessage("正在连接 Project_R Workbench 服务");
    try {
      const health = await apiRequest<HealthResponse>({ baseUrl: normalized }, "/health");
      if (health.status === "ok") {
        setCheckState("ok");
        setMessage("已连接到 Project_R Workbench 服务");
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
      <main className="gate-content">
        <header className="gate-brand" aria-labelledby="gate-title">
          <img className="gate-logo" src={ravenLogo} alt={`${APP_NAME} logo`} />
          <h1 id="gate-title" className="gate-title">{APP_NAME}</h1>
        </header>

        <section className="gate-card" aria-labelledby="gate-card-title">
          <div className="gate-card-header">
            <h2 id="gate-card-title">服务连接配置</h2>
            <p>请输入 Project_R 后端服务地址以进行初始化</p>
          </div>

          <div className={`gate-status ${checkState}`}>
            <div className="gate-pulse" aria-hidden="true">
              {checkState === "ok" ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              ) : checkState === "error" ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              ) : checkState === "checking" ? (
                <span className="gate-spinner" />
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
        </section>
      </main>
    </div>
  );
}
