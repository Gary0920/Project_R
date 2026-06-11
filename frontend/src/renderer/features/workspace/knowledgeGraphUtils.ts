export type NativeContextKind = "graph" | "timeline" | "backlinks";

export type NativeContextListItem = {
  id: string;
  title: string;
  subtitle: string;
  detail: string;
};

export interface GraphLayoutNode {
  id: string;
  degree: number;
  isFocus: boolean;
  isNeighbor: boolean;
}

export interface Position {
  x: number;
  y: number;
}

export function nativeText(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

export function nativePick(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = nativeText(record[key]);
    if (value) return value;
  }
  return "";
}

export function nativeResultItems(payload: Record<string, unknown> | undefined, kind: NativeContextKind): NativeContextListItem[] {
  const result = payload?.result;
  if (!Array.isArray(result)) return [];
  return result
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    .slice(0, 8)
    .map((item, index) => {
      if (kind === "timeline") {
        const date = nativePick(item, ["date", "created_at", "timestamp"]);
        const summary = nativePick(item, ["summary", "title", "event", "text"]) || `Timeline entry ${index + 1}`;
        const source = nativePick(item, ["source", "source_file", "citation", "page_slug"]);
        const detail = nativePick(item, ["detail", "description", "content"]);
        return {
          id: nativePick(item, ["id"]) || `${kind}-${index}`,
          title: date ? `${date} · ${summary}` : summary,
          subtitle: source || "timeline",
          detail,
        };
      }
      if (kind === "backlinks") {
        const from = nativePick(item, ["from", "from_slug", "from_page", "source_slug", "slug"]);
        const relation = nativePick(item, ["link_type", "relation_type", "type"]);
        const title = nativePick(item, ["title", "from_title", "source_title"]) || from || `Backlink ${index + 1}`;
        const evidence = nativePick(item, ["evidence", "anchor", "context", "to"]);
        return {
          id: nativePick(item, ["id"]) || `${kind}-${index}`,
          title,
          subtitle: [relation, from].filter(Boolean).join(" · ") || "backlink",
          detail: evidence,
        };
      }
      const from = nativePick(item, ["from", "from_slug", "source", "source_slug"]);
      const to = nativePick(item, ["to", "to_slug", "target", "target_slug", "slug"]);
      const relation = nativePick(item, ["link_type", "relation_type", "type"]);
      const depth = nativePick(item, ["depth", "distance"]);
      return {
        id: nativePick(item, ["id"]) || `${kind}-${index}`,
        title: [from, to].filter(Boolean).join(" -> ") || nativePick(item, ["title", "slug"]) || `Graph path ${index + 1}`,
        subtitle: [relation, depth ? `depth ${depth}` : ""].filter(Boolean).join(" · ") || "graph",
        detail: nativePick(item, ["evidence", "summary", "context"]),
      };
    });
}

export function nativeResultCount(payload: Record<string, unknown> | undefined) {
  const result = payload?.result;
  if (Array.isArray(result)) return result.length;
  if (result && typeof result === "object") return Object.keys(result).length;
  return payload?.status === "ok" ? 0 : 0;
}

export function graphEventTimestamp(date?: string) {
  if (!date) return null;
  const parsed = Date.parse(date);
  return Number.isNaN(parsed) ? null : parsed;
}

export function graphEventGroupLabel(date?: string) {
  const timestamp = graphEventTimestamp(date);
  if (timestamp === null) return "未标日期";
  const value = new Date(timestamp);
  return `${value.getFullYear()}年${String(value.getMonth() + 1).padStart(2, "0")}月`;
}

export function graphForceLayout(
  nodes: Array<{ id: string; degree: number; isFocus: boolean; isNeighbor: boolean; entityType?: string }>,
  edges: Array<{ from: string; to: string }>,
  width: number,
  height: number,
  baseRadius: number,
): Map<string, Position> {
  const cx = width / 2;
  const cy = height / 2;
  const positions = new Map<string, Position>();
  const edgeSet = new Set(edges.map((e) => `${e.from}::${e.to}`));

  const maxDegree = Math.max(1, ...nodes.map((n) => n.degree));
  const nodeCount = nodes.length;

  const adjacency = new Map<string, Set<string>>();
  for (const edge of edges) {
    let set = adjacency.get(edge.from);
    if (!set) {
      set = new Set();
      adjacency.set(edge.from, set);
    }
    set.add(edge.to);
    set = adjacency.get(edge.to);
    if (!set) {
      set = new Set();
      adjacency.set(edge.to, set);
    }
    set.add(edge.from);
  }

  const visited = new Set<string>();
  const ordered: string[] = [];
  const focusNode = nodes.find((n) => n.isFocus);
  if (focusNode) {
    const queue = [focusNode.id];
    visited.add(focusNode.id);
    while (queue.length > 0) {
      const current = queue.shift()!;
      ordered.push(current);
      for (const neighbor of adjacency.get(current) ?? []) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          queue.push(neighbor);
        }
      }
    }
  }
  for (const node of nodes) {
    if (!visited.has(node.id)) ordered.push(node.id);
  }

  const orderMap = new Map(ordered.map((id, i) => [id, i]));

  const entityTypes = [...new Set(nodes.map((n) => n.entityType ?? "page").filter(Boolean))];
  const entityTypeAngleOffset = new Map(entityTypes.map((type, i) => [type, (i / entityTypes.length) * Math.PI * 0.5]));

  for (const node of nodes) {
    if (node.isFocus) {
      positions.set(node.id, { x: cx, y: cy });
      continue;
    }
    const order = orderMap.get(node.id) ?? 0;
    const total = nodeCount;
    const angle = -Math.PI / 2 + (order / Math.max(1, total)) * Math.PI * 2
      + (entityTypeAngleOffset.get(node.entityType ?? "page") ?? 0);
    const degreeFactor = Math.max(0.3, node.degree / maxDegree);
    const ring = Math.floor(order / Math.max(1, Math.ceil(total / 3)));
    const ringRadius = baseRadius * (0.45 + degreeFactor * 0.55 + ring * 0.12);
    positions.set(node.id, {
      x: cx + Math.cos(angle) * ringRadius,
      y: cy + Math.sin(angle) * ringRadius,
    });
  }

  const iterations = Math.min(12, Math.max(8, nodeCount));
  for (let iter = 0; iter < iterations; iter++) {
    const displacements = new Map<string, { dx: number; dy: number }>();
    for (const node of nodes) {
      displacements.set(node.id, { dx: 0, dy: 0 });
    }

    for (let i = 0; i < nodeCount; i++) {
      for (let j = i + 1; j < nodeCount; j++) {
        const a = nodes[i], b = nodes[j];
        const posA = positions.get(a.id), posB = positions.get(b.id);
        if (!posA || !posB) continue;
        const dx = posA.x - posB.x, dy = posA.y - posB.y;
        const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
        const connected = edgeSet.has(`${a.id}::${b.id}`) || edgeSet.has(`${b.id}::${a.id}`);
        const forceMagnitude = connected
          ? -Math.sqrt(dist) * 0.18
          : (baseRadius * 3.0) / (dist * dist);
        const force = forceMagnitude;
        const dispA = displacements.get(a.id)!;
        const dispB = displacements.get(b.id)!;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        dispA.dx += fx; dispA.dy += fy;
        dispB.dx -= fx; dispB.dy -= fy;
      }
    }

    for (let i = 0; i < nodeCount; i++) {
      for (let j = i + 1; j < nodeCount; j++) {
        const a = nodes[i], b = nodes[j];
        if (a.isFocus || b.isFocus) continue;
        if (a.entityType !== b.entityType || !a.entityType) continue;
        const posA = positions.get(a.id), posB = positions.get(b.id);
        if (!posA || !posB) continue;
        const dx = posA.x - posB.x, dy = posA.y - posB.y;
        const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
        const attract = dist * 0.004;
        const dispA = displacements.get(a.id)!;
        const dispB = displacements.get(b.id)!;
        dispA.dx -= (dx / dist) * attract;
        dispA.dy -= (dy / dist) * attract;
        dispB.dx += (dx / dist) * attract;
        dispB.dy += (dy / dist) * attract;
      }
    }

    for (const node of nodes) {
      if (node.isFocus) continue;
      const pos = positions.get(node.id)!;
      const disp = displacements.get(node.id)!;
      const dx = cx - pos.x, dy = cy - pos.y;
      const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
      const gravity = node.isNeighbor ? 0.12 : 0.06;
      disp.dx += (dx / dist) * gravity;
      disp.dy += (dy / dist) * gravity;
    }

    let maxDisp = 0;
    const cooling = 1 / Math.sqrt(iter + 1);
    for (const node of nodes) {
      if (node.isFocus) continue;
      const pos = positions.get(node.id)!;
      const disp = displacements.get(node.id)!;
      const mag = Math.sqrt(disp.dx * disp.dx + disp.dy * disp.dy);
      maxDisp = Math.max(maxDisp, mag);
      const clamp = Math.min(mag, baseRadius * 0.4) / Math.max(1, mag);
      pos.x += disp.dx * clamp * cooling;
      pos.y += disp.dy * clamp * cooling;
      pos.x = Math.max(20, Math.min(width - 20, pos.x));
      pos.y = Math.max(20, Math.min(height - 20, pos.y));
    }
    if (maxDisp < 0.25 && iter > 3) break;
  }

  return positions;
}

export function graphEntityTypeColor(entityType: string): string {
  const palette: Record<string, string> = {
    client_profile: "#4f46e5",
    client_profile_unresolved: "#818cf8",
    customer_project: "#0891b2",
    customer_project_profile_unresolved: "#22d3ee",
    customer_company: "#059669",
    customer_company_profile_unresolved: "#34d399",
    project: "#d97706",
    event: "#dc2626",
    source_event: "#dc2626",
    customer_source_event_unresolved: "#f87171",
    meeting: "#9333ea",
    page: "#6b7280",
    unresolved_entity: "#9ca3af",
  };
  const key = (entityType ?? "page").toLowerCase();
  for (const [prefix, color] of Object.entries(palette)) {
    if (key.includes(prefix)) return color;
  }
  return palette.page;
}

export function crmEntityLabel(entityType: string | null | undefined) {
  const key = (entityType ?? "").toLowerCase();
  if (key.includes("person") || key.includes("client") || key.includes("contact")) return "联系人";
  if (key.includes("company")) return "公司";
  if (key.includes("project")) return "项目";
  if (key.includes("event") || key.includes("meeting")) return "沟通记录";
  if (key.includes("unresolved")) return "待确认";
  return "资料";
}

export function crmRelationLabel(relationType: string | null | undefined) {
  const key = (relationType ?? "").toLowerCase();
  if (key.includes("person") || key.includes("people")) return "关联联系人";
  if (key.includes("company")) return "关联公司";
  if (key.includes("project")) return "关联项目";
  if (key.includes("event")) return "相关事件";
  if (key.includes("affiliated")) return "所属公司";
  return "关联";
}

export function crmShortSource(value: string | null | undefined) {
  const text = (value ?? "").replace(/\\/g, "/").trim();
  if (!text) return "";
  const filename = text.split("/").pop() || text;
  return filename.replace(/\.(md|markdown|txt|eml)$/i, "");
}

export function graphCanvasPointSized(
  index: number,
  total: number,
  hasFocusNode: boolean,
  width: number,
  height: number,
  baseRadius: number,
  _nodes?: Array<{ id: string; degree: number; isFocus: boolean; isNeighbor: boolean }>,
  _edges?: Array<{ from: string; to: string }>,
) {
  const centerX = width / 2;
  const centerY = height / 2;
  if ((hasFocusNode && index === 0) || (!hasFocusNode && total === 1)) {
    return { x: centerX, y: centerY };
  }
  const ringIndex = hasFocusNode ? index - 1 : index;
  const ringTotal = Math.max(1, hasFocusNode ? total - 1 : total);
  const angle = -Math.PI / 2 + (ringIndex / ringTotal) * Math.PI * 2;
  const radius = ringTotal > 8 && ringIndex % 2 === 1 ? baseRadius * 1.22 : baseRadius;
  return {
    x: centerX + Math.cos(angle) * radius,
    y: centerY + Math.sin(angle) * radius,
  };
}

export function graphCanvasPoint(index: number, total: number, hasFocusNode: boolean) {
  return graphCanvasPointSized(index, total, hasFocusNode, 340, 216, 72);
}

export function graphCanvasLabel(value: string) {
  const text = value.trim();
  return text.length > 12 ? `${text.slice(0, 11)}...` : text;
}

export function graphCanvasLargeLabel(value: string) {
  const text = value.trim();
  return text.length > 18 ? `${text.slice(0, 17)}...` : text;
}

export function clampGraphCanvasScale(value: number) {
  return Math.max(0.7, Math.min(2.4, value));
}

export function graphCitationString(citation: Record<string, unknown> | null | undefined, key: string) {
  const value = citation?.[key];
  return typeof value === "string" ? value.trim() : "";
}

export function normalizeGraphSourcePath(value: string | null | undefined) {
  const text = (value ?? "").trim().replace(/\\/g, "/");
  if (!text || text.startsWith("/") || /^[A-Za-z]:\//.test(text) || text.includes("..")) return "";
  const first = text.split("/")[0]?.toLowerCase() ?? "";
  if ([".git", ".trash", "derived", "manifests", ".pending_review"].includes(first)) return "";
  return text;
}

export function graphPreviewSourcePath(
  item: { source_file?: string | null; citation?: Record<string, unknown> | null } | null | undefined,
) {
  if (!item) return "";
  return (
    normalizeGraphSourcePath(item.source_file)
    || normalizeGraphSourcePath(graphCitationString(item.citation, "source_file"))
  );
}
