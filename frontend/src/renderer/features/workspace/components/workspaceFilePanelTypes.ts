import type { WorkspaceFileItemResponse } from "../../../shared/api/types";

export type WorkspaceFileContextMenu = {
  item?: WorkspaceFileItemResponse;
  targetDirectory: string;
  kind: "item" | "blank";
  x: number;
  y: number;
};

export type WorkspaceClipboardItem = {
  action: "copy" | "cut";
  item: WorkspaceFileItemResponse;
};
