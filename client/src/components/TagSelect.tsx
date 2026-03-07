import { useState, useRef, useCallback } from "react";
import { X, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

export const PRESET_FILE_EXTENSIONS = [
  ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".csv", ".txt", ".html", ".epub",
];

export const PRESET_LANGUAGES = [
  "en", "zh", "fr", "de", "ja", "ko", "es", "pt", "it", "ru",
];

export const PRESET_COUNTRIES = [
  "US", "CN", "GB", "DE", "FR", "JP", "KR", "AU", "CA", "IN",
];

interface TagSelectProps {
  value: string[];
  onChange: (value: string[]) => void;
  presets?: string[];
  placeholder?: string;
  testId?: string;
}

export default function TagSelect({ value, onChange, presets = [], placeholder = "Add custom...", testId }: TagSelectProps) {
  const [customInput, setCustomInput] = useState("");
  const [showInput, setShowInput] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const toggleTag = useCallback((tag: string) => {
    if (value.includes(tag)) {
      onChange(value.filter((v) => v !== tag));
    } else {
      onChange([...value, tag]);
    }
  }, [value, onChange]);

  const addCustom = useCallback(() => {
    const trimmed = customInput.trim();
    if (trimmed && !value.includes(trimmed)) {
      onChange([...value, trimmed]);
    }
    setCustomInput("");
  }, [customInput, value, onChange]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addCustom();
    } else if (e.key === "Escape") {
      setShowInput(false);
      setCustomInput("");
    }
  };

  const customValues = value.filter((v) => !presets.includes(v));

  return (
    <div className="space-y-2" data-testid={testId}>
      {presets.length > 0 && (
        <div className="flex flex-wrap gap-1.5" data-testid={testId ? `${testId}-presets` : undefined}>
          {presets.map((tag) => {
            const selected = value.includes(tag);
            return (
              <button
                key={tag}
                type="button"
                onClick={() => toggleTag(tag)}
                className={cn(
                  "inline-flex items-center px-2 py-1 rounded-md text-xs font-medium transition-colors border",
                  selected
                    ? "bg-primary/15 text-primary border-primary/30 hover:bg-primary/25"
                    : "bg-muted/50 text-muted-foreground border-border hover:bg-muted hover:text-foreground"
                )}
                data-testid={testId ? `${testId}-tag-${tag}` : undefined}
              >
                {tag}
              </button>
            );
          })}
        </div>
      )}

      {customValues.length > 0 && (
        <div className="flex flex-wrap gap-1.5" data-testid={testId ? `${testId}-custom` : undefined}>
          {customValues.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium bg-accent text-accent-foreground border border-border"
            >
              {tag}
              <button
                type="button"
                onClick={() => toggleTag(tag)}
                className="hover:text-destructive transition-colors"
                data-testid={testId ? `${testId}-remove-${tag}` : undefined}
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-1.5">
        {showInput ? (
          <div className="flex items-center gap-1.5 flex-1">
            <input
              ref={inputRef}
              type="text"
              value={customInput}
              onChange={(e) => setCustomInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onBlur={() => {
                if (customInput.trim()) addCustom();
                setShowInput(false);
              }}
              placeholder={placeholder}
              className="flex-1 px-2.5 py-1.5 text-xs rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
              autoFocus
              data-testid={testId ? `${testId}-custom-input` : undefined}
            />
          </div>
        ) : (
          <button
            type="button"
            onClick={() => {
              setShowInput(true);
              setTimeout(() => inputRef.current?.focus(), 0);
            }}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-muted border border-dashed border-border transition-colors"
            data-testid={testId ? `${testId}-add-custom` : undefined}
          >
            <Plus className="w-3 h-3" />
            {placeholder}
          </button>
        )}
      </div>

      {value.length > 0 && (
        <p className="text-[11px] text-muted-foreground" data-testid={testId ? `${testId}-count` : undefined}>
          {value.length} selected
        </p>
      )}
    </div>
  );
}
