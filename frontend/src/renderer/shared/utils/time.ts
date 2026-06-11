export function parseApiDate(value: string | number | Date | null | undefined): Date {
  if (value instanceof Date) return value;
  if (typeof value === "number") return new Date(value);
  const text = String(value ?? "").trim();
  if (!text) return new Date(Number.NaN);
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(text);
  return new Date(hasTimezone ? text : `${text}Z`);
}
