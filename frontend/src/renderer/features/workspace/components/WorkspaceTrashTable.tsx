import type { WorkspaceFileItemResponse } from "../../../shared/api/types";
import { parseApiDate } from "../../../shared/utils/time";
import { formatSize } from "../workspaceFilePanelUtils";

type WorkspaceTrashTableProps = {
  items: WorkspaceFileItemResponse[];
  onRestore: (item: WorkspaceFileItemResponse) => void | Promise<void>;
  onPermanentDelete: (item: WorkspaceFileItemResponse) => void | Promise<void>;
};

export function WorkspaceTrashTable({
  items,
  onRestore,
  onPermanentDelete,
}: WorkspaceTrashTableProps) {
  return (
    <div className="workspace-trash-table">
      {items.map((item) => (
        <div className="workspace-trash-row" key={`${item.id}-${item.path}`}>
          <span className="workspace-trash-name">{item.name}</span>
          <span className="workspace-trash-path">{item.path}</span>
          <span>{formatSize(item.size)}</span>
          <span>{item.deleted_at ? parseApiDate(item.deleted_at).toLocaleString("zh-CN") : ""}</span>
          <div>
            <button disabled={!item.can_restore} onClick={() => void onRestore(item)} type="button">还原</button>
            <button disabled={!item.can_delete} onClick={() => void onPermanentDelete(item)} type="button">删除</button>
          </div>
        </div>
      ))}
    </div>
  );
}
