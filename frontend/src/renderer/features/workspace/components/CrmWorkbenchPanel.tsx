import type { ReactNode, Ref } from "react";

import type { Workspace } from "../state";
import { BrainIcon, SearchIcon, WorkspaceIcon } from "../../../shared/icons/LineIcons";

type CrmWorkbenchPanelProps = {
  activeWorkspace: Workspace | null;
  auxiliaryPanelMaxWidth: number;
  auxiliaryPanelRef: Ref<HTMLElement>;
  auxiliaryPanelResizing: boolean;
  auxiliaryPanelWidth: number;
  onClose: () => void;
  onOpenCustomerIntelligence: () => void;
  onOpenWorkspaceFiles: () => void;
  resizeHandle: ReactNode;
};

export function CrmWorkbenchPanel({
  activeWorkspace,
  auxiliaryPanelMaxWidth,
  auxiliaryPanelRef,
  auxiliaryPanelResizing,
  auxiliaryPanelWidth,
  onClose,
  onOpenCustomerIntelligence,
  onOpenWorkspaceFiles,
  resizeHandle,
}: CrmWorkbenchPanelProps) {
  const isCustomerWorkspace = activeWorkspace?.workspace_kind === "customer";

  return (
    <aside
      aria-label="CRM 工作台"
      className={`utility-side-pane auxiliary-side-pane crm-workbench-pane ${auxiliaryPanelResizing ? "is-resizing" : ""}`}
      ref={auxiliaryPanelRef}
      style={{ flexBasis: auxiliaryPanelWidth, maxWidth: auxiliaryPanelMaxWidth, width: auxiliaryPanelWidth }}
    >
      {resizeHandle}
      <header className="utility-side-header">
        <div>
          <h2>CRM</h2>
          <p>客户情报入口</p>
        </div>
        <button className="prompt-panel-close" onClick={onClose} type="button">×</button>
      </header>
      <div className="crm-workbench-body">
        <section className="crm-workbench-hero">
          <span className="crm-workbench-icon"><BrainIcon /></span>
          <div>
            <h3>CRM 总览</h3>
            <p>CRM 是客户情报大区。先在这里进入总览，再通过搜索或选择具体客户、联系人、公司与项目查看画像详情。</p>
          </div>
        </section>
        <div className="crm-workbench-flow" aria-label="CRM 使用路径">
          <span><strong>1</strong><small>进入客户情报</small></span>
          <span><strong>2</strong><small>搜索或选择对象</small></span>
          <span><strong>3</strong><small>查看画像、关系和互动</small></span>
        </div>
        <div className="crm-workbench-actions">
          <button className="business-tool-button" disabled={!isCustomerWorkspace} onClick={onOpenCustomerIntelligence} type="button">
            <BrainIcon />
            <span>客户情报</span>
          </button>
          <button className="business-tool-button" disabled={!isCustomerWorkspace} onClick={onOpenWorkspaceFiles} type="button">
            <WorkspaceIcon />
            <span>CRM 文件管理</span>
          </button>
        </div>
        <div className="crm-workbench-sections">
          <section>
            <span><SearchIcon /></span>
            <div>
              <strong>客户检索</strong>
              <p>在客户情报中搜索客户、联系人、公司、项目或近期事件。</p>
            </div>
          </section>
          <section>
            <span><BrainIcon /></span>
            <div>
              <strong>画像详情</strong>
              <p>选中具体对象后查看业务摘要、关系网、时间线和来源证据。</p>
            </div>
          </section>
          <section>
            <span><WorkspaceIcon /></span>
            <div>
              <strong>资料文件</strong>
              <p>上传、录入、回收站和文件治理仍在 CRM 文件管理中处理。</p>
            </div>
          </section>
        </div>
        <p className="crm-workbench-note">
          {isCustomerWorkspace
            ? "当前处于 CRM 工作区。客户情报负责画像、关系和互动；CRM 文件管理只负责源文件和录入治理。"
            : "切换到 CRM 工作区后，可使用客户情报能力。"}
        </p>
      </div>
    </aside>
  );
}
