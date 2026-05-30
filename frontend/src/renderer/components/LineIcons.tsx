import type { CSSProperties, HTMLAttributes } from "react";

import archiveUrl from "iconoir/icons/archive.svg";
import attachmentUrl from "iconoir/icons/attachment.svg";
import bellUrl from "iconoir/icons/bell-notification.svg";
import brainUrl from "iconoir/icons/brain-electricity.svg";
import checkUrl from "iconoir/icons/check.svg";
import chatUrl from "iconoir/icons/chat-lines.svg";
import chevronDownUrl from "iconoir/icons/nav-arrow-down.svg";
import chevronLeftUrl from "iconoir/icons/nav-arrow-left.svg";
import chevronRightUrl from "iconoir/icons/nav-arrow-right.svg";
import copyUrl from "iconoir/icons/copy.svg";
import editUrl from "iconoir/icons/edit-pencil.svg";
import folderUrl from "iconoir/icons/folder.svg";
import logoutUrl from "iconoir/icons/log-out.svg";
import maximizeUrl from "iconoir/icons/square.svg";
import minimizeUrl from "iconoir/icons/minus.svg";
import moreUrl from "iconoir/icons/more-horiz.svg";
import moveUrl from "iconoir/icons/data-transfer-both.svg";
import noteUrl from "iconoir/icons/page-edit.svg";
import pinUrl from "iconoir/icons/pin.svg";
import plusUrl from "iconoir/icons/plus.svg";
import refreshUrl from "iconoir/icons/refresh-double.svg";
import restoreUrl from "iconoir/icons/collapse.svg";
import searchUrl from "iconoir/icons/search.svg";
import sendUrl from "iconoir/icons/send-diagonal.svg";
import settingsUrl from "iconoir/icons/settings.svg";
import shieldUrl from "iconoir/icons/shield.svg";
import splitUrl from "iconoir/icons/horizontal-split.svg";
import sparkUrl from "iconoir/icons/sparks.svg";
import textSquareUrl from "iconoir/icons/text-square.svg";
import trashUrl from "iconoir/icons/trash.svg";
import xmarkUrl from "iconoir/icons/xmark.svg";

type IconProps = HTMLAttributes<HTMLSpanElement>;

function IconoirIcon({ className, style, url, ...props }: IconProps & { url: string }) {
  return (
    <span
      aria-hidden="true"
      className={`iconoir-mask ${className ?? ""}`}
      style={{ "--icon-url": `url("${url}")`, ...style } as CSSProperties}
      {...props}
    />
  );
}

export function ChatIcon(props: IconProps) { return <IconoirIcon url={chatUrl} {...props} />; }
export function AgentIcon(props: IconProps) { return <IconoirIcon url={sparkUrl} {...props} />; }
export function PlusIcon(props: IconProps) { return <IconoirIcon url={plusUrl} {...props} />; }
export function SearchIcon(props: IconProps) { return <IconoirIcon url={searchUrl} {...props} />; }
export function CheckIcon(props: IconProps) { return <IconoirIcon url={checkUrl} {...props} />; }
export function MoreIcon(props: IconProps) { return <IconoirIcon url={moreUrl} {...props} />; }
export function WorkspaceIcon(props: IconProps) { return <IconoirIcon url={folderUrl} {...props} />; }
export function ChevronDownIcon(props: IconProps) { return <IconoirIcon url={chevronDownUrl} {...props} />; }
export function ChevronLeftIcon(props: IconProps) { return <IconoirIcon url={chevronLeftUrl} {...props} />; }
export function ChevronRightIcon(props: IconProps) { return <IconoirIcon url={chevronRightUrl} {...props} />; }
export function EditIcon(props: IconProps) { return <IconoirIcon url={editUrl} {...props} />; }
export function TrashIcon(props: IconProps) { return <IconoirIcon url={trashUrl} {...props} />; }
export function PinIcon(props: IconProps) { return <IconoirIcon url={pinUrl} {...props} />; }
export function ArchiveIcon(props: IconProps) { return <IconoirIcon url={archiveUrl} {...props} />; }
export function MoveIcon(props: IconProps) { return <IconoirIcon url={moveUrl} {...props} />; }
export function SettingsIcon(props: IconProps) { return <IconoirIcon url={settingsUrl} {...props} />; }
export function SplitIcon(props: IconProps) { return <IconoirIcon url={splitUrl} {...props} />; }
export function PromptIcon(props: IconProps) { return <IconoirIcon url={textSquareUrl} {...props} />; }
export function LogoutIcon(props: IconProps) { return <IconoirIcon url={logoutUrl} {...props} />; }
export function MinimizeIcon(props: IconProps) { return <IconoirIcon url={minimizeUrl} {...props} />; }
export function MaximizeIcon(props: IconProps) { return <IconoirIcon url={maximizeUrl} {...props} />; }
export function StopIcon(props: IconProps) { return <IconoirIcon url={maximizeUrl} {...props} />; }
export function RestoreIcon(props: IconProps) { return <IconoirIcon url={restoreUrl} {...props} />; }
export function NoteIcon(props: IconProps) { return <IconoirIcon url={noteUrl} {...props} />; }
export function CopyIcon(props: IconProps) { return <IconoirIcon url={copyUrl} {...props} />; }
export function RefreshIcon(props: IconProps) { return <IconoirIcon url={refreshUrl} {...props} />; }
export function PaperclipIcon(props: IconProps) { return <IconoirIcon url={attachmentUrl} {...props} />; }
export function BrainIcon(props: IconProps) { return <IconoirIcon url={brainUrl} {...props} />; }
export function SendIcon(props: IconProps) { return <IconoirIcon url={sendUrl} {...props} />; }
export function XmarkIcon(props: IconProps) { return <IconoirIcon url={xmarkUrl} {...props} />; }
export function ShieldIcon(props: IconProps) { return <IconoirIcon url={shieldUrl} {...props} />; }
export function BellIcon(props: IconProps) { return <IconoirIcon url={bellUrl} {...props} />; }
