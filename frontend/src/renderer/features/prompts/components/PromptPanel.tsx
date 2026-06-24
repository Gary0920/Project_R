import { useEffect, useMemo, useState } from "react";

import type { CompanyPromptResponse } from "../../../shared/api/types";
import { PROJECT_R_BUILTIN_PROMPT } from "../constants";
import { CheckIcon, PlusIcon, PromptIcon, SearchIcon } from "../../../shared/icons/LineIcons";

export type PromptSource = "builtin" | "company" | "user";

export type PromptOption = {
  id: string;
  source: PromptSource;
  name: string;
  description: string;
  content: string;
};

export type PromptPanelProps = {
  selectedPromptId: string;
  companyPrompts: CompanyPromptResponse[];
  userPrompts: UserPromptRecord[];
  onSelect: (prompt: PromptOption) => void;
  onCreateUserPrompt: (name: string, content: string) => Promise<UserPromptRecord | null>;
  onUpdateUserPrompt: (id: string, name: string, content: string) => Promise<UserPromptRecord | null>;
  onDeleteUserPrompt: (id: string) => Promise<void>;
  onClose: () => void;
  embedded?: boolean;
};

function toPromptId(source: PromptSource, id: string) {
  return `${source}:${id}`;
}

function sourceLabel(source: PromptSource) {
  if (source === "builtin") return "内置";
  if (source === "company") return "公司";
  return "本机";
}

function matchesPromptSearch(prompt: PromptOption, query: string) {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return true;
  return (
    prompt.name.toLowerCase().includes(normalizedQuery)
    || prompt.description.toLowerCase().includes(normalizedQuery)
    || prompt.content.toLowerCase().includes(normalizedQuery)
  );
}

function PromptRow({
  prompt,
  previewed,
  selected,
  onApply,
  onPreview,
}: {
  prompt: PromptOption;
  previewed: boolean;
  selected: boolean;
  onApply: (prompt: PromptOption) => void;
  onPreview: (prompt: PromptOption) => void;
}) {
  const canQuickApply = prompt.source !== "builtin";
  const visibleSelected = selected && canQuickApply;
  const visiblePreviewed = previewed && canQuickApply;

  return (
    <div className={`prompt-row ${visibleSelected ? "is-selected" : ""} ${visiblePreviewed ? "is-previewed" : ""} ${!canQuickApply ? "is-readonly" : ""}`}>
      <button
        className="prompt-row-main"
        onClick={() => onPreview(prompt)}
        onDoubleClick={() => {
          if (canQuickApply) onApply(prompt);
        }}
        onFocus={() => onPreview(prompt)}
        title={prompt.name}
        type="button"
      >
        <span className="prompt-row-icon"><PromptIcon /></span>
        <span className="prompt-row-copy">
          <span className="prompt-row-title">
            <span className="prompt-row-name">{prompt.name}</span>
            <span className={`prompt-source-badge is-${prompt.source}`}>{sourceLabel(prompt.source)}</span>
          </span>
        </span>
      </button>
      {canQuickApply ? (
        <button
          className={`prompt-row-quick-apply ${selected ? "is-selected" : ""}`}
          onClick={(event) => {
            event.stopPropagation();
            onApply(prompt);
          }}
          title={selected ? "已应用" : "快速应用"}
          type="button"
        >
          <CheckIcon />
        </button>
      ) : null}
    </div>
  );
}

export function PromptPanel({
  selectedPromptId,
  companyPrompts,
  userPrompts,
  onSelect,
  onCreateUserPrompt,
  onUpdateUserPrompt,
  onDeleteUserPrompt,
  onClose,
  embedded = false,
}: PromptPanelProps) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [companySearchQuery, setCompanySearchQuery] = useState("");
  const [previewPromptId, setPreviewPromptId] = useState(selectedPromptId);
  const [detailOpen, setDetailOpen] = useState(false);
  const [editingPromptId, setEditingPromptId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editContent, setEditContent] = useState("");

  const builtInPrompts: PromptOption[] = useMemo(() => [PROJECT_R_BUILTIN_PROMPT], []);
  const companyOptions: PromptOption[] = companyPrompts.map((prompt) => ({
    id: prompt.id,
    source: "company",
    name: prompt.name,
    description: prompt.description,
    content: prompt.content,
  }));
  const userOptions: PromptOption[] = userPrompts.map((prompt) => ({
    id: prompt.id,
    source: "user",
    name: prompt.name,
    description: "仅本机可用",
    content: prompt.content,
  }));
  const allPrompts = [...builtInPrompts, ...companyOptions, ...userOptions];
  const fallbackPrompt = allPrompts.find((prompt) => toPromptId(prompt.source, prompt.id) === selectedPromptId) ?? PROJECT_R_BUILTIN_PROMPT;
  const previewPrompt = allPrompts.find((prompt) => toPromptId(prompt.source, prompt.id) === previewPromptId) ?? fallbackPrompt;
  const filteredCompanyOptions = companyOptions.filter((prompt) => matchesPromptSearch(prompt, companySearchQuery));
  const editingPreview = editingPromptId === toPromptId(previewPrompt.source, previewPrompt.id) && previewPrompt.source === "user";
  const hasDetailActions = creating || editingPreview || previewPrompt.source !== "builtin";

  useEffect(() => {
    if (allPrompts.some((prompt) => toPromptId(prompt.source, prompt.id) === previewPromptId)) return;
    setPreviewPromptId(toPromptId(fallbackPrompt.source, fallbackPrompt.id));
    setEditingPromptId(null);
  }, [allPrompts, fallbackPrompt, previewPromptId]);

  function previewPromptOption(prompt: PromptOption) {
    setPreviewPromptId(toPromptId(prompt.source, prompt.id));
    setEditingPromptId(null);
    setCreating(false);
    setDetailOpen(true);
  }

  async function handleCreate() {
    const cleanName = name.trim();
    const cleanContent = content.trim();
    if (!cleanName || !cleanContent) return;
    const saved = await onCreateUserPrompt(cleanName, cleanContent);
    setName("");
    setContent("");
    setCreating(false);
    if (saved) setPreviewPromptId(toPromptId("user", saved.id));
  }

  function startCreatingPrompt() {
    setCreating(true);
    setEditingPromptId(null);
    setName("");
    setContent("");
    setDetailOpen(true);
  }

  function startEditingPreview() {
    if (previewPrompt.source !== "user") return;
    setCreating(false);
    setEditingPromptId(toPromptId(previewPrompt.source, previewPrompt.id));
    setEditName(previewPrompt.name);
    setEditContent(previewPrompt.content);
    setDetailOpen(true);
  }

  async function saveEditingPreview() {
    if (previewPrompt.source !== "user") return;
    const cleanName = editName.trim();
    const cleanContent = editContent.trim();
    if (!cleanName || !cleanContent) return;
    const saved = await onUpdateUserPrompt(previewPrompt.id, cleanName, cleanContent);
    if (saved) {
      setPreviewPromptId(toPromptId("user", saved.id));
      setEditingPromptId(null);
    }
  }

  function renderRows(items: PromptOption[], emptyText?: string) {
    return items.length > 0 ? (
      items.map((prompt) => {
        const promptId = toPromptId(prompt.source, prompt.id);
        return (
          <PromptRow
            key={promptId}
            prompt={prompt}
            previewed={previewPromptId === promptId}
            selected={prompt.source !== "builtin" && selectedPromptId === promptId}
            onApply={onSelect}
            onPreview={previewPromptOption}
          />
        );
      })
    ) : (
      <div className="prompt-empty">{emptyText ?? "暂无提示词"}</div>
    );
  }

  function renderCompanySection() {
    const hasCompanyPrompts = companyOptions.length > 0;
    const emptyText = !hasCompanyPrompts
      ? "后端暂未返回公司预设"
      : companySearchQuery.trim()
        ? "没有匹配的提示词"
        : "暂无提示词";

    return (
      <section className="prompt-section">
        <div className="prompt-section-head">
          <div className="prompt-section-title">公司预设</div>
          <div className="prompt-section-search">
            <SearchIcon />
            <input
              aria-label="搜索公司预设提示词"
              onChange={(event) => setCompanySearchQuery(event.target.value)}
              placeholder="搜索标题或概述"
              type="search"
              value={companySearchQuery}
            />
          </div>
        </div>
        {renderRows(filteredCompanyOptions, emptyText)}
      </section>
    );
  }

  function renderSection(title: string, items: PromptOption[], emptyText?: string) {
    return (
      <section className="prompt-section">
        <div className="prompt-section-title">{title}</div>
        {renderRows(items, emptyText)}
      </section>
    );
  }

  const panel = (
    <aside className={`prompt-panel ${embedded ? "is-embedded" : ""}`} onClick={(event) => event.stopPropagation()}>
      <header className="prompt-panel-header">
        <div>
          <h2>提示词</h2>
        </div>
        <button className="prompt-panel-close" onClick={onClose} type="button">×</button>
      </header>

      <div className={`prompt-panel-body prompt-master-detail ${detailOpen ? "is-detail-open" : ""}`}>
        <div className="prompt-master-pane" aria-label="提示词列表">
          {renderSection("Project_R 内置", builtInPrompts)}
          {renderCompanySection()}
          {renderSection("用户自定义", userOptions, "本机暂无自定义提示词")}
          <div className="prompt-create-block">
            <button className="prompt-create-trigger" onClick={startCreatingPrompt} type="button">
              <PlusIcon />
              <span>新建本机提示词</span>
            </button>
          </div>
        </div>

        <section className="prompt-detail-pane" aria-label="提示词详情">
          <div className={`prompt-detail-toolbar ${hasDetailActions ? "" : "is-actions-empty"}`}>
            <button className="prompt-detail-back" onClick={() => setDetailOpen(false)} type="button">返回列表</button>
            <div className="prompt-detail-toolbar-actions">
              {creating ? (
                <>
                  <button className="prompt-action-button" onClick={() => setCreating(false)} type="button">取消</button>
                  <button className="prompt-action-button is-apply" disabled={!name.trim() || !content.trim()} onClick={() => void handleCreate()} type="button">
                    保存
                  </button>
                </>
              ) : editingPreview ? (
                <>
                  <button className="prompt-action-button" onClick={() => setEditingPromptId(null)} type="button">取消</button>
                  <button className="prompt-action-button is-apply" disabled={!editName.trim() || !editContent.trim()} onClick={() => void saveEditingPreview()} type="button">
                    保存
                  </button>
                </>
              ) : (
                <>
                  {previewPrompt.source === "user" ? (
                    <>
                      <button className="prompt-action-button" onClick={startEditingPreview} type="button">编辑</button>
                      <button className="prompt-action-button is-danger" onClick={() => void onDeleteUserPrompt(previewPrompt.id)} type="button">删除</button>
                    </>
                  ) : null}
                  {previewPrompt.source !== "builtin" ? (
                    <button className="prompt-action-button is-apply" onClick={() => onSelect(previewPrompt)} type="button">
                      应用到会话
                    </button>
                  ) : null}
                </>
              )}
            </div>
          </div>
          <div className="prompt-detail-scroll">
            {creating ? (
              <div className="prompt-preview-card">
                <div className="prompt-preview-header">
                  <div>
                    <span className="prompt-source-badge is-user">本机</span>
                    <h3>新建本机提示词</h3>
                  </div>
                </div>
                <p>保存后只在本机可用，不上传后端。</p>
                <div className="prompt-preview-edit">
                  <input
                    autoFocus
                    className="prompt-create-name"
                    onChange={(event) => setName(event.target.value)}
                    placeholder="提示词名称"
                    value={name}
                  />
                  <textarea
                    className="prompt-create-content"
                    onChange={(event) => setContent(event.target.value)}
                    placeholder="输入系统提示词内容..."
                    value={content}
                  />
                </div>
              </div>
            ) : (
              <div className="prompt-preview-card">
                <div className="prompt-preview-header">
                  <div>
                    <span className={`prompt-source-badge is-${previewPrompt.source}`}>{sourceLabel(previewPrompt.source)}</span>
                    <h3>{previewPrompt.name}</h3>
                  </div>
                  {selectedPromptId === toPromptId(previewPrompt.source, previewPrompt.id) ? <span className="prompt-preview-applied">已应用</span> : null}
                </div>
                <p>{previewPrompt.description || "无简介"}</p>
                {editingPreview ? (
                  <div className="prompt-preview-edit">
                    <input
                      className="prompt-create-name"
                      onChange={(event) => setEditName(event.target.value)}
                      value={editName}
                    />
                    <textarea
                      className="prompt-create-content"
                      onChange={(event) => setEditContent(event.target.value)}
                      value={editContent}
                    />
                  </div>
                ) : (
                  <pre className="prompt-preview-content">{previewPrompt.content}</pre>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    </aside>
  );

  if (embedded) return panel;

  return (
    <div className="prompt-panel-overlay" onClick={onClose}>
      {panel}
    </div>
  );
}

export function getPromptOptionId(prompt: Pick<PromptOption, "source" | "id">) {
  return toPromptId(prompt.source, prompt.id);
}
