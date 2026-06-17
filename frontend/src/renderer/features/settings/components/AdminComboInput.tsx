import { useState, type ReactNode } from "react";

export type AdminComboOption = {
  value: string;
  label: string;
  meta?: string;
  badge?: string;
  disabled?: boolean;
};

function filterAdminComboOptions(options: AdminComboOption[], value: string, limit = 8) {
  const normalized = value.trim().toLowerCase();
  const filtered = normalized
    ? options.filter((option) => (
      option.label.toLowerCase().includes(normalized)
      || option.value.toLowerCase().includes(normalized)
      || (option.meta ?? "").toLowerCase().includes(normalized)
      || (option.badge ?? "").toLowerCase().includes(normalized)
    ))
    : options;
  return filtered.slice(0, limit);
}

export function AdminComboInput({
  value,
  options,
  placeholder,
  disabled,
  icon,
  className = "",
  onChange,
  onSelect,
  onCommit,
}: {
  value: string;
  options: AdminComboOption[];
  placeholder: string;
  disabled?: boolean;
  icon?: ReactNode;
  className?: string;
  onChange: (value: string) => void;
  onSelect?: (value: string) => void;
  onCommit?: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const visibleOptions = filterAdminComboOptions(options, value);
  const hasMenu = open && !disabled && visibleOptions.length > 0;

  return (
    <div className={`admin-combo-input workspace-suggest-input ${className}`}>
      <label className={icon ? "has-icon" : ""}>
        {icon}
        <input
          disabled={disabled}
          placeholder={placeholder}
          value={value}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              onCommit?.(value);
              setOpen(false);
            }
            if (event.key === "Escape") {
              setOpen(false);
            }
          }}
        />
      </label>
      {hasMenu ? (
        <div className="workspace-suggest-menu admin-combo-menu">
          {visibleOptions.map((option) => (
            <button
              disabled={option.disabled}
              key={`${option.value}-${option.badge ?? ""}`}
              onMouseDown={(event) => {
                event.preventDefault();
                onChange(option.value);
                onSelect?.(option.value);
                setOpen(false);
              }}
              type="button"
            >
              <span>
                <strong>{option.label}</strong>
                {option.meta ? <small>{option.meta}</small> : null}
              </span>
              {option.badge ? <em>{option.badge}</em> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
