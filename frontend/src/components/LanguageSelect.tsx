import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LANGUAGES } from "@/lib/languages";

export function LanguageSelect({
  value,
  onValueChange,
  extraOption,
  id,
  className,
  ariaLabel,
}: {
  value: string;
  onValueChange: (value: string) => void;
  /** e.g. { value: "auto", label: "Detect automatically" } */
  extraOption?: { value: string; label: string };
  id?: string;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger id={id} className={className} aria-label={ariaLabel}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {extraOption && (
          <>
            <SelectItem value={extraOption.value}>{extraOption.label}</SelectItem>
            <SelectSeparator />
          </>
        )}
        {LANGUAGES.map((lang) => (
          <SelectItem key={lang.code} value={lang.code}>
            <span className="inline-flex items-baseline gap-2">
              <span>{lang.name}</span>
              {lang.code !== "en" && <span className="text-muted-foreground">{lang.nativeName}</span>}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
