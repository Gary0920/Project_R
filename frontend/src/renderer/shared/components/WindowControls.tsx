import { useEffect, useState } from "react";

import { MaximizeIcon, MinimizeIcon, RestoreIcon, XmarkIcon } from "../icons/LineIcons";

export function WindowControls() {
  const [isMaximized, setIsMaximized] = useState(false);
  const windowApi = window.projectR?.window;
  const isDesktopWindow = Boolean(windowApi);

  useEffect(() => {
    if (!windowApi) return undefined;

    void windowApi.isMaximized().then(setIsMaximized).catch(() => setIsMaximized(false));
    return windowApi.onStateChange((state) => setIsMaximized(state.isMaximized));
  }, [windowApi]);

  if (!isDesktopWindow) {
    return null;
  }

  return (
    <div className="window-controls titlebar-no-drag" aria-label="窗口控制">
      <button className="window-control-btn" onClick={() => void windowApi?.minimize()} title="最小化" type="button">
        <MinimizeIcon />
      </button>
      <button className="window-control-btn" onClick={() => void windowApi?.toggleMaximize()} title={isMaximized ? "还原" : "最大化"} type="button">
        {isMaximized ? <RestoreIcon /> : <MaximizeIcon />}
      </button>
      <button className="window-control-btn window-control-close" onClick={() => void windowApi?.close()} title="关闭" type="button">
        <XmarkIcon />
      </button>
    </div>
  );
}
