import type { SourceEvidenceFilter } from "../sourceEvidenceTypes";
import { sourceEvidenceFilterLabel } from "../sourceEvidence";

export type SourceEvidenceFiltersProps = {
  activeFilter: SourceEvidenceFilter;
  filters: SourceEvidenceFilter[];
  onChange: (filter: SourceEvidenceFilter) => void;
};

export function SourceEvidenceFilters({ activeFilter, filters, onChange }: SourceEvidenceFiltersProps) {
  if (filters.length <= 1) return null;
  return (
    <div className="source-evidence-filters" aria-label="本轮引用来源筛选">
      {filters.map((filter) => (
        <button
          className={`source-evidence-filter ${activeFilter === filter ? "is-active" : ""}`}
          key={filter}
          onClick={() => onChange(filter)}
          type="button"
        >
          {sourceEvidenceFilterLabel(filter)}
        </button>
      ))}
    </div>
  );
}
