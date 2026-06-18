import { useState } from "react";

import type { CompanyPromptResponse } from "../../../shared/api/types";
import { PROJECT_R_BUILTIN_PROMPT } from "../constants";
import { CheckIcon, PlusIcon, PromptIcon, SearchIcon, TrashIcon } from "../../../shared/icons/LineIcons";

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
  onCreateUserPrompt: (name: string, content: string) => Promise<void>;
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
  );
}

function PromptRow({
  prompt,
  visibleDescriptionId,
  selectedPromptId,
  onSelect,
  onDeleteUserPrompt,
  onShowDescription,
}: {
  prompt: PromptOption;
  visibleDescriptionId: string | null;
  selectedPromptId: string;
  onSelect: (prompt: PromptOption) => void;
  onDeleteUserPrompt: (id: string) => Promise<void>;
  onShowDescription: (id: string) => void;
}) {
  const promptId = toPromptId(prompt.source, prompt.id);
  const selected = selectedPromptId === promptId;
  const description = prompt.description || prompt.content;
  const descriptionVisible = visibleDescriptionId === promptId;

  function showDescription() {
    onShowDescription(promptId);
  }

  return (
    <div
      className={`prompt-row ${selected ? "is-selected" : ""} ${descriptionVisible ? "is-description-visible" : ""}`}
      onMouseEnter={showDescription}
    >
      <button
        className="prompt-row-main"
        onClick={() => {
          showDescription();
          onSelect(prompt);
        }}
        onFocus={showDescription}
        type="button"
      >
        <span className="prompt-row-icon"><PromptIcon /></span>
        <span className="prompt-row-copy">
          <span className="prompt-row-title">
            {prompt.name}
            <span className={`prompt-source-badge is-${prompt.source}`}>{sourceLabel(prompt.source)}</span>
          </span>
          <span className="prompt-row-description">{description}</span>
        </span>
        {selected ? <CheckIcon className="prompt-row-check" /> : null}
      </button>
      {prompt.source === "user" ? (
        <button
          className="prompt-row-delete"
          onClick={() => void onDeleteUserPrompt(prompt.id)}
          title="删除本机提示词"
          type="button"
        >
          <TrashIcon />
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
  onDeleteUserPrompt,
  onClose,
  embedded = false,
}: PromptPanelProps) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [visibleDescriptionId, setVisibleDescriptionId] = useState<string | null>(null);
  const [companySearchQuery, setCompanySearchQuery] = useState("");

  const builtInPrompts: PromptOption[] = [PROJECT_R_BUILTIN_PROMPT];
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
  const filteredCompanyOptions = companyOptions.filter((prompt) => matchesPromptSearch(prompt, companySearchQuery));

  async function handleCreate() {
    const cleanName = name.trim();
    const cleanContent = content.trim();
    if (!cleanName || !cleanContent) return;
    await onCreateUserPrompt(cleanName, cleanContent);
    setName("");
    setContent("");
    setCreating(false);
  }

  function renderCompanySection() {
    const hasCompanyPrompts = companyOptions.length > 0;
    const items = filteredCompanyOptions;
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
        {items.length > 0 ? (
          items.map((prompt) => (
            <PromptRow
              key={`${prompt.source}:${prompt.id}`}
              prompt={prompt}
              visibleDescriptionId={visibleDescriptionId}
              selectedPromptId={selectedPromptId}
              onSelect={onSelect}
              onDeleteUserPrompt={onDeleteUserPrompt}
              onShowDescription={setVisibleDescriptionId}
            />
          ))
        ) : (
          <div className="prompt-empty">{emptyText}</div>
        )}
      </section>
    );
  }

  function renderSection(title: string, items: PromptOption[], emptyText?: string) {
    return (
      <section className="prompt-section">
        <div className="prompt-section-title">{title}</div>
        {items.length > 0 ? (
          items.map((prompt) => (
            <PromptRow
              key={`${prompt.source}:${prompt.id}`}
              prompt={prompt}
              visibleDescriptionId={visibleDescriptionId}
              selectedPromptId={selectedPromptId}
              onSelect={onSelect}
              onDeleteUserPrompt={onDeleteUserPrompt}
              onShowDescription={setVisibleDescriptionId}
            />
          ))
        ) : (
          <div className="prompt-empty">{emptyText ?? "暂无提示词"}</div>
        )}
      </section>
    );
  }

  const panel = (
    <aside className={`prompt-panel ${embedded ? "is-embedded" : ""}`} onClick={(event) => event.stopPropagation()}>
        <header className="prompt-panel-header">
          <div>
            <h2>提示词</h2>
            <p>当前会话 system prompt</p>
          </div>
          <button className="prompt-panel-close" onClick={onClose} type="button">×</button>
        </header>

        <div className="prompt-panel-body" onMouseLeave={() => setVisibleDescriptionId(null)}>
          {renderSection("Project_R 内置", builtInPrompts)}
          {renderCompanySection()}
          {renderSection("用户自定义", userOptions, "本机暂无自定义提示词")}

          <div className="prompt-create-block">
            {creating ? (
              <>
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
                <div className="prompt-create-actions">
                  <button className="button-ghost" onClick={() => setCreating(false)} type="button">取消</button>
                  <button className="button-primary" disabled={!name.trim() || !content.trim()} onClick={() => void handleCreate()} type="button">
                    保存
                  </button>
                </div>
              </>
            ) : (
              <button className="prompt-create-trigger" onClick={() => setCreating(true)} type="button">
                <PlusIcon />
                <span>新建本机提示词</span>
              </button>
            )}
          </div>
        </div>
      </aside>
  );

  if (embedded) {
    return panel;
  }

  return (
    <div className="prompt-panel-overlay" onClick={onClose}>
      {panel}
    </div>
  );
}

export function getPromptOptionId(prompt: Pick<PromptOption, "source" | "id">) {
  return toPromptId(prompt.source, prompt.id);
}
