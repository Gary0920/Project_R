import { type RefObject, useEffect, useMemo, useRef, useState } from "react";

export interface JumpBarMessage {
  id: number;
  role: string;
  content: string;
}

interface JumpBarProps {
  /** Messages for the active session — only user messages are shown as dots */
  messages: JumpBarMessage[];
  /** Ref to the scrollable message container — used to find [data-turn] elements */
  scrollRef: RefObject<HTMLElement | null>;
}

export function JumpBar({ messages, scrollRef }: JumpBarProps) {
  const [hovered, setHovered] = useState<number | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const previewTop = useRef(0);
  const [showPreview, setShowPreview] = useState(false);

  // Only user messages, each with a stable id
  const items = useMemo(
    () =>
      messages
        .filter(
          (m): m is { id: number; role: "user"; content: string } =>
            m.role === "user" && typeof m.content === "string",
        )
        .map((m) => ({ id: m.id, text: m.content.slice(0, 80) })),
    [messages],
  );

  // Keep the last (most recent) user message as active
  useEffect(() => {
    if (items.length > 0) setActive(items[items.length - 1]!.id);
  }, [items]);

  // Scroll the active dot into view inside the bar
  useEffect(() => {
    if (active === null) return;
    const el = barRef.current?.querySelector(`[data-turn="${active}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [active]);

  // Don't render if there's only 0-1 user messages
  if (items.length < 2) return null;

  const hoverIdx = hovered !== null ? items.findIndex((v) => v.id === hovered) : -1;
  const hoverText =
    hovered !== null ? items.find((v) => v.id === hovered)?.text : null;

  const onMove = (e: React.MouseEvent) => {
    const el = barRef.current;
    if (!el) return;
    const q = el.querySelectorAll<HTMLElement>(".jump-item");
    const barRect = el.getBoundingClientRect();
    let closest = -1;
    let closestDist = Infinity;
    q.forEach((item, i) => {
      const r = item.getBoundingClientRect();
      const midY = r.top + r.height / 2;
      const dist = Math.abs(e.clientY - midY);
      if (dist < closestDist) {
        closestDist = dist;
        closest = i;
        previewTop.current = midY - barRect.top;
      }
    });
    if (closest >= 0 && closest < items.length) {
      const id = items[closest]?.id;
      if (id !== undefined) {
        setHovered(id);
        setShowPreview(true);
      }
    }
  };

  const scrollTo = (id: number) => {
    setActive(id);
    scrollRef.current
      ?.querySelector(`[data-turn="${id}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const dotProps = (
    idx: number,
    id: number,
  ): { style: React.CSSProperties; "data-d"?: string } => {
    const isActive = active === id;
    if (hoverIdx < 0) {
      return {
        style: {
          width: isActive ? 18 : 12,
          background: isActive ? "hsl(var(--accent))" : undefined,
        },
      };
    }
    const d = Math.abs(idx - hoverIdx);
    const width = d === 0 ? 32 : d === 1 ? 20 : d === 2 ? 14 : isActive ? 18 : 12;
    const background =
      d <= 2 ? undefined : isActive ? "hsl(var(--accent))" : undefined;
    return {
      style: { width, transitionDelay: `${d * 20}ms`, background },
      "data-d": d <= 2 ? String(d) : undefined,
    };
  };

  return (
    <div
      className="jump-bar"
      ref={barRef}
      onMouseMove={onMove}
      onMouseLeave={() => {
        setHovered(null);
        setShowPreview(false);
      }}
    >
      <div className="jump-scroll">
        {items.map((item, idx) => (
          <div
            className="jump-item"
            key={item.id}
            data-turn={item.id}
            onClick={() => scrollTo(item.id)}
          >
            <div className="jump-dot" {...dotProps(idx, item.id)} />
          </div>
        ))}
      </div>
      {showPreview && hoverText && (
        <div className="jump-preview" style={{ top: previewTop.current }}>
          <span className="jump-text">{hoverText}</span>
        </div>
      )}
    </div>
  );
}
