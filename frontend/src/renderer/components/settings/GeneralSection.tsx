import type { Dispatch, RefObject, SetStateAction } from "react";

import type { CurrentUserResponse } from "../../api/types";
import { CameraIcon, EditIcon } from "../LineIcons";

type PreferenceState = {
  completionSound: boolean;
  autoArchiveDays: string;
  floatingPinBar: boolean;
  theme: "system" | "light" | "dark";
  dingTalkWebhook: string;
  dingTalkToken: string;
  shortcuts: Record<string, string>;
};

type ProfileDraft = {
  nickname: string;
  avatar: string;
};

type PickerPosition = {
  top: number;
  left: number;
};

export type GeneralSectionProps = {
  avatarPickerRef: RefObject<HTMLDivElement | null>;
  avatarRef: RefObject<HTMLDivElement | null>;
  commonEmojis: string[];
  currentUser: CurrentUserResponse | null;
  fileInputRef: RefObject<HTMLInputElement | null>;
  formatOptionalDate: (value?: string | null) => string;
  handleAvatarImageUpload: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleSelectEmoji: (emoji: string) => Promise<void>;
  isEditingName: boolean;
  nameInput: string;
  onSaveNickname: (nickname: string) => Promise<void>;
  pickerPos: PickerPosition | null;
  preferences: PreferenceState;
  profileAvatarUrl: string | null;
  profileDraft: ProfileDraft;
  profileLocked: boolean;
  setIsEditingName: Dispatch<SetStateAction<boolean>>;
  setMessage: (message: string) => void;
  setNameInput: Dispatch<SetStateAction<string>>;
  setPickerPos: Dispatch<SetStateAction<PickerPosition | null>>;
  setShowAvatarPicker: Dispatch<SetStateAction<boolean>>;
  showAvatarPicker: boolean;
  updatePreference: (next: Partial<PreferenceState>) => void;
};

export function GeneralSection({
  avatarPickerRef,
  avatarRef,
  commonEmojis,
  currentUser,
  fileInputRef,
  formatOptionalDate,
  handleAvatarImageUpload,
  handleSelectEmoji,
  isEditingName,
  nameInput,
  onSaveNickname,
  pickerPos,
  preferences,
  profileAvatarUrl,
  profileDraft,
  profileLocked,
  setIsEditingName,
  setMessage,
  setNameInput,
  setPickerPos,
  setShowAvatarPicker,
  showAvatarPicker,
  updatePreference,
}: GeneralSectionProps) {
  const profileLockMessage = "系统内置管理员账号，头像和昵称由系统维护。";

  return (
    <>
      <div className="settings-section">
        <div className="settings-section-header">
          <h3>用户档案</h3>
          <p>{profileLocked ? "系统内置管理员账号为只读档案" : "设置你的头像和显示名称"}</p>
        </div>
        <div className="settings-card">
          <div className="settings-card-row" style={{ gap: 16, position: "relative" }}>
            <div
              ref={avatarRef}
              className={`profile-avatar ${profileLocked ? "is-locked" : ""}`}
              onClick={() => {
                if (profileLocked) {
                  setMessage(profileLockMessage);
                  return;
                }
                const rect = avatarRef.current?.getBoundingClientRect();
                if (rect) {
                  const pickerWidth = 280;
                  const viewportPadding = 12;
                  const maxLeft = Math.max(
                    viewportPadding,
                    window.innerWidth - pickerWidth - viewportPadding,
                  );
                  const left = Math.min(
                    Math.max(viewportPadding, rect.left),
                    maxLeft,
                  );
                  setPickerPos({ top: rect.bottom + 8, left });
                }
                setShowAvatarPicker((prev) => !prev);
              }}
              title={profileLocked ? profileLockMessage : "更换头像"}
              style={{ cursor: profileLocked ? "default" : "pointer", position: "relative", width: 64, height: 64, borderRadius: "20%", overflow: "hidden", flexShrink: 0, display: "grid", placeItems: "center", background: "hsl(var(--muted))", fontSize: 28 }}
            >
              {profileAvatarUrl ? (
                <img src={profileAvatarUrl} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : (
                <span>{profileDraft.avatar || "👤"}</span>
              )}
              {!profileLocked ? (
                <div
                  style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", background: "rgba(0,0,0,0.4)", opacity: 0, transition: "opacity 0.15s", pointerEvents: "none" }}
                  className="profile-avatar-overlay"
                >
                  <CameraIcon className="profile-avatar-camera" />
                </div>
              ) : null}
            </div>

            {!profileLocked && showAvatarPicker && pickerPos && (
              <div className="profile-avatar-picker" ref={avatarPickerRef} style={{ top: pickerPos.top, left: pickerPos.left }}>
                <div className="profile-avatar-picker-grid">
                  {commonEmojis.map((emoji) => (
                    <button key={emoji} onClick={() => handleSelectEmoji(emoji)} type="button">
                      {emoji}
                    </button>
                  ))}
                </div>
                <div className="profile-avatar-picker-upload">
                  <button onClick={() => fileInputRef.current?.click()} type="button">
                    上传自定义图片
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/gif,image/webp"
                    style={{ display: "none" }}
                    onChange={handleAvatarImageUpload}
                  />
                </div>
              </div>
            )}

            <div style={{ flex: 1, minWidth: 0 }}>
              {isEditingName ? (
                <input
                  type="text"
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  onBlur={() => {
                    const trimmed = nameInput.trim();
                    if (trimmed && trimmed !== currentUser?.nickname) {
                      void onSaveNickname(trimmed).catch(() => {});
                    }
                    setIsEditingName(false);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.currentTarget.blur();
                    } else if (e.key === "Escape") {
                      setNameInput(currentUser?.nickname ?? "");
                      setIsEditingName(false);
                    }
                  }}
                  autoFocus
                  style={{ fontSize: 18, fontWeight: 600, color: "hsl(var(--foreground))", background: "transparent", border: "none", borderBottom: "2px solid hsl(var(--foreground))", outline: "none", width: "100%", maxWidth: 240, padding: "2px 0" }}
                />
              ) : (
                profileLocked ? (
                  <div className="profile-name-readonly">
                    <span>{profileDraft.nickname || currentUser?.nickname || "未设置昵称"}</span>
                    <small>系统维护</small>
                  </div>
                ) : (
                  <button
                    onClick={() => {
                      setNameInput(profileDraft.nickname);
                      setIsEditingName(true);
                    }}
                    style={{ fontSize: 18, fontWeight: 600, color: "hsl(var(--foreground))", background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left" }}
                  >
                    <span>{profileDraft.nickname || currentUser?.nickname || "未设置昵称"}</span>
                    <EditIcon className="profile-name-edit-icon" />
                  </button>
                )
              )}
              <div className="profile-meta-row">
                <span>账号 {currentUser?.username ?? "-"}</span>
                <span>最近登录 {formatOptionalDate(currentUser?.last_login_at)}</span>
              </div>
              {profileLocked ? <p className="profile-lock-note">{profileLockMessage}</p> : null}
            </div>
          </div>
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-header">
          <h3>通用设置</h3>
          <p>应用的基本配置</p>
        </div>
        <div className="settings-card">
          <div className="settings-option-row">
            <div>
              <strong>界面语言</strong>
              <span>更多语言支持即将推出</span>
            </div>
            <select disabled value="zh-CN">
              <option value="zh-CN">简体中文</option>
            </select>
          </div>
          <div className="settings-option-row">
            <div>
              <strong>任务完成音效</strong>
              <span>Agent 工作流完成后播放提示音</span>
            </div>
            <label className="toggle-switch">
              <input
                checked={preferences.completionSound}
                onChange={(event) => updatePreference({ completionSound: event.target.checked })}
                type="checkbox"
              />
              <span className="toggle-switch-slider" />
            </label>
          </div>
          <div className="settings-option-row">
            <div>
              <strong>自动归档</strong>
              <span>按最后更新时间清理侧栏会话</span>
            </div>
            <select
              value={preferences.autoArchiveDays}
              onChange={(event) => updatePreference({ autoArchiveDays: event.target.value })}
            >
              <option value="disabled">禁用</option>
              <option value="7">7 天</option>
              <option value="14">14 天</option>
              <option value="30">30 天</option>
              <option value="60">60 天</option>
            </select>
          </div>
          <div className="settings-option-row">
            <div>
              <strong>消息悬浮置顶条</strong>
              <span>会话滚动时保留置顶提示入口</span>
            </div>
            <label className="toggle-switch">
              <input
                checked={preferences.floatingPinBar}
                onChange={(event) => updatePreference({ floatingPinBar: event.target.checked })}
                type="checkbox"
              />
              <span className="toggle-switch-slider" />
            </label>
          </div>
          <div className="settings-option-row">
            <div>
              <strong>外观主题</strong>
              <span>亮色、暗色或跟随系统</span>
            </div>
            <select
              value={preferences.theme}
              onChange={(event) => updatePreference({ theme: event.target.value as PreferenceState["theme"] })}
            >
              <option value="system">跟随系统</option>
              <option value="light">亮色</option>
              <option value="dark">暗色</option>
            </select>
          </div>
        </div>
      </div>
    </>
  );
}
