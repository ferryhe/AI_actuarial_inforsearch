import { Loader2 } from "lucide-react";
import { cloneElement, isValidElement, type ReactNode } from "react";
import TagSelect from "./TagSelect";

export function FormField({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  const child = isValidElement<{ testId?: string; id?: string; "data-testid"?: string; "aria-labelledby"?: string; "aria-describedby"?: string }>(children) ? children : null;
  const id = child?.props.id || child?.props.testId || child?.props["data-testid"];
  const hintId = hint && id ? `hint-${id}` : undefined;
  const canAssociate = child && id && (child.type === InputField || child.type === SelectField || child.type === TagSelect || ["input", "select", "textarea"].includes(String(child.type)));
  return (
    <div className="space-y-1.5">
      {canAssociate ? <label id={`label-${id}`} htmlFor={child?.type === TagSelect ? undefined : id} className="text-xs font-medium text-muted-foreground">{label}</label> : <div className="text-xs font-medium text-muted-foreground">{label}</div>}
      {canAssociate ? cloneElement(child, { id, "aria-labelledby": child?.type === TagSelect ? `label-${id}` : undefined, "aria-describedby": hintId || child.props["aria-describedby"] }) : children}
      {hint && <p id={hintId} className="text-[11px] text-muted-foreground/70">{hint}</p>}
    </div>
  );
}

export function InputField({ value, onChange, placeholder, type = "text", min, max, testId, id, "aria-describedby": ariaDescribedBy }: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string; min?: number; max?: number; testId?: string; id?: string; "aria-describedby"?: string;
}) {
  return (
    <input type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} min={min} max={max}
      className="w-full min-h-[48px] px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
      id={id || testId} aria-describedby={ariaDescribedBy} data-testid={testId} />
  );
}

export function SelectField({ value, onChange, options, testId, id, "aria-describedby": ariaDescribedBy }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; testId?: string; id?: string; "aria-describedby"?: string;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className="w-full min-h-[48px] px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
      id={id || testId} aria-describedby={ariaDescribedBy} data-testid={testId}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export function CheckboxField({ checked, onChange, label, testId }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; testId?: string;
}) {
  return (
    <label className="flex min-h-[48px] items-center gap-2 text-sm cursor-pointer">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="rounded" data-testid={testId} />
      {label}
    </label>
  );
}

export function RunButton({ onClick, disabled, submitting, label, testId = "button-run-task", "aria-describedby": ariaDescribedBy }: {
  onClick: () => void; disabled: boolean; submitting: boolean; label: string; testId?: string; "aria-describedby"?: string;
}) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="w-full min-h-[48px] flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
      aria-describedby={ariaDescribedBy} data-testid={testId}>
      {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
      {label}
    </button>
  );
}

export function StatsBanner({ items }: { items: { label: string; value: string | number | null | undefined }[] }) {
  const valid = items.filter((i) => i.value != null);
  if (valid.length === 0) return null;
  return (
    <div className="rounded-lg border border-border bg-muted/40 px-4 py-3 grid grid-cols-2 sm:grid-cols-3 gap-3" data-testid="stats-banner">
      {valid.map((item) => (
        <div key={item.label}>
          <p className="text-[11px] text-muted-foreground">{item.label}</p>
          <p className="text-sm font-semibold">{item.value}</p>
        </div>
      ))}
    </div>
  );
}
