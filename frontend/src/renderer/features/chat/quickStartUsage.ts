const QUICK_START_USAGE_KEY = "project-r:quick-start-usage";

export function getQuickStartUsageCounts(): Record<string, number> {
  try {
    const raw = localStorage.getItem(QUICK_START_USAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const counts: Record<string, number> = {};
    for (const [key, value] of Object.entries(parsed)) {
      const count = Number(value);
      if (Number.isFinite(count) && count > 0) counts[key] = count;
    }
    return counts;
  } catch {
    return {};
  }
}

export function recordQuickStartUsage(id: string) {
  const normalized = id.trim();
  if (!normalized) return;
  try {
    const counts = getQuickStartUsageCounts();
    counts[normalized] = (counts[normalized] ?? 0) + 1;
    localStorage.setItem(QUICK_START_USAGE_KEY, JSON.stringify(counts));
  } catch {
    // localStorage may be unavailable in restricted shells.
  }
}

export function sortQuickStartItems<T extends { id: string }>(items: T[]): T[] {
  const counts = getQuickStartUsageCounts();
  return [...items].sort((left, right) => {
    const leftCount = counts[left.id] ?? 0;
    const rightCount = counts[right.id] ?? 0;
    if (rightCount !== leftCount) return rightCount - leftCount;
    return items.indexOf(left) - items.indexOf(right);
  });
}
