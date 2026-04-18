import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function FormField({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground/70">{hint}</p>}
    </div>
  );
}

export function InputField({ value, onChange, placeholder, type = "text", testId }: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string; testId?: string;
}) {
  return (
    <input type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
      className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
      data-testid={testId} />
  );
}

export function SelectField({ value, onChange, options, testId }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; testId?: string;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
      data-testid={testId}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export function CheckboxField({ checked, onChange, label, testId }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; testId?: string;
}) {
  return (
    <label className="flex items-center gap-2 text-sm cursor-pointer">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="rounded" data-testid={testId} />
      {label}
    </label>
  );
}

export function RunButton({ onClick, disabled, submitting, label }: {
  onClick: () => void; disabled: boolean; submitting: boolean; label: string;
}) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
      data-testid="button-run-task">
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
