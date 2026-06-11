import type { MouseEvent } from "react";

import {
  formatSize,
  getRagStatusMeta,
  type WorkspaceFilePreview,
} from "../workspaceFilePanelUtils";
import type { WorkspaceFileItemResponse } from "../../../shared/api/types";
import { parseApiDate } from "../../../shared/utils/time";
import { ArchiveIcon, XmarkIcon } from "../../../shared/icons/LineIcons";

type WorkspaceFilePreviewSidecarProps = {
  preview: WorkspaceFilePreview;
  resizing: boolean;
  onClose: () => void;
  onDownload: (item: WorkspaceFileItemResponse) => void | Promise<void>;
  onResizeStart: (event: MouseEvent<HTMLDivElement>) => void;
};

export function WorkspaceFilePreviewSidecar({
  preview,
  resizing,
  onClose,
  onDownload,
  onResizeStart,
}: WorkspaceFilePreviewSidecarProps) {
  return (
    <aside className={`workspace-file-preview-sidecar is-${preview.kind} ${resizing ? "is-resizing" : ""}`} aria-label="文件预览">
      <div
        aria-label="调整预览面板宽度"
        aria-orientation="vertical"
        className="workspace-file-preview-resize-handle"
        onMouseDown={onResizeStart}
        role="separator"
        title="拖动调整预览面板宽度"
      />
      <header className="workspace-file-preview-sidecar-header">
        <div>
          <strong>预览</strong>
          <span>{preview.item.name}</span>
        </div>
        <div className="workspace-file-preview-actions">
          <button aria-label="下载文件" className="workspace-file-action" onClick={() => void onDownload(preview.item)} title="下载文件" type="button"><ArchiveIcon /></button>
          <button aria-label="关闭预览" className="workspace-file-action" onClick={onClose} title="关闭预览" type="button"><XmarkIcon /></button>
        </div>
      </header>
      <div className="workspace-file-preview-stage">
        {preview.status === "loading" ? <span>正在加载预览...</span> : null}
        {preview.status === "failed" ? <span>{preview.error || "文件预览失败"}</span> : null}
        {preview.status === "ready" && preview.kind === "image" && preview.objectUrl ? (
          <img alt={preview.item.name} src={preview.objectUrl} />
        ) : null}
        {preview.status === "ready" && preview.kind === "pdf" && preview.objectUrl ? (
          <iframe src={preview.objectUrl} title={preview.item.name} />
        ) : null}
        {preview.status === "ready" && preview.text != null ? (
          <pre>{preview.text}</pre>
        ) : null}
        {preview.status === "ready" && !["image", "pdf"].includes(preview.kind) && preview.text == null ? (
          <span>当前格式暂不支持内嵌预览。</span>
        ) : null}
      </div>
      <section className="workspace-file-preview-details" aria-label="详细信息">
        <h3>详细信息</h3>
        <dl>
          <div><dt>类型</dt><dd>{preview.kind === "image" ? "图片文件" : preview.kind === "pdf" ? "PDF 文件" : preview.kind === "code" ? "文本/代码文件" : "文件"}</dd></div>
          <div><dt>大小</dt><dd>{formatSize(preview.item.size)}</dd></div>
          <div><dt>上传人</dt><dd>{preview.item.uploader_name || (preview.item.uploaded_by ? `用户 #${preview.item.uploaded_by}` : "-")}</dd></div>
          <div><dt>位置</dt><dd title={preview.item.path}>{preview.item.path}</dd></div>
          <div><dt>修改日期</dt><dd>{preview.item.updated_at ? parseApiDate(preview.item.updated_at).toLocaleString("zh-CN") : "-"}</dd></div>
          <div><dt>入库状态</dt><dd>{getRagStatusMeta(preview.item.rag_status).label}</dd></div>
        </dl>
      </section>
    </aside>
  );
}
