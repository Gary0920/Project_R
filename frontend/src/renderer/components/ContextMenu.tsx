import { useEffect, useRef, type MouseEvent, type ReactNode } from "react";

export type ContextMenuItemDef =
  | {
    type: "item";
    label: string;
    action?: () => void;
    checked?: boolean;
    children?: ContextMenuItemDef[];
    destructive?: boolean;
    disabled?: boolean;
    icon?: ReactNode;
  }
  | { type: "separator" };

export type ContextMenuProps = {
  x: number;
  y: number;
  items: ContextMenuItemDef[];
  onClose: () => void;
};

export function ContextMenu({ x, y, items, onClose }: ContextMenuProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handleClick(event: globalThis.MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        onClose();
      }
    }
    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("mousedown", handleClick, true);
    window.addEventListener("keydown", onEscape);
    return () => {
      window.removeEventListener("mousedown", handleClick, true);
      window.removeEventListener("keydown", onEscape);
    };
  }, [onClose]);

  const style: React.CSSProperties = { left: x, top: y };
  // Clamp to viewport
  if (typeof window !== "undefined") {
    if (x + 230 > window.innerWidth) style.left = Math.max(8, x - 230);
    if (y + 260 > window.innerHeight) style.top = Math.max(8, y - 260);
  }

  function renderItems(menuItems: ContextMenuItemDef[], level = 0) {
    return menuItems.map((item, i) =>
      item.type === "separator" ? (
        <div className="context-menu-separator" key={`sep-${level}-${i}`} />
      ) : (
        <div
          aria-disabled={item.disabled || undefined}
          className={[
            "context-menu-item",
            item.children?.length ? "has-submenu" : "",
            item.destructive ? "is-destructive" : "",
            item.disabled ? "is-disabled" : "",
          ].filter(Boolean).join(" ")}
          key={`${item.label}-${level}-${i}`}
          onClick={(event) => {
            if (item.children?.length || item.disabled || !item.action) return;
            event.stopPropagation();
            item.action();
            onClose();
          }}
        >
          <span className="context-menu-item-main">
            {item.icon ? <span className="context-menu-icon">{item.icon}</span> : null}
            <span>{item.label}</span>
          </span>
          {item.checked ? <span className="context-menu-check">✓</span> : null}
          {item.children?.length ? <span className="context-menu-arrow">›</span> : null}
          {item.children?.length ? (
            <div className="context-submenu">
              {renderItems(item.children, level + 1)}
            </div>
          ) : null}
        </div>
      ),
    );
  }

  return (
    <>
      <div className="context-menu-overlay" onClick={onClose} />
      <div className="context-menu" ref={ref} style={style}>
        {renderItems(items)}
      </div>
    </>
  );
}

export function useContextMenu(
  state: { x: number; y: number; items: ContextMenuItemDef[] } | null,
  setState: (v: null) => void,
) {
  if (!state) return null;
  return (
    <ContextMenu x={state.x} y={state.y} items={state.items} onClose={() => setState(null)} />
  );
}
