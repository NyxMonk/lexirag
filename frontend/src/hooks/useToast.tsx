import { CheckCircle2, AlertCircle, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

type ToastTone = "default" | "error";

interface Toast {
  id: number;
  title: string;
  description?: string;
  tone: ToastTone;
}

interface ToastContextValue {
  toast: (t: { title: string; description?: string; tone?: ToastTone }) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((all) => all.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback<ToastContextValue["toast"]>(
    ({ title, description, tone = "default" }) => {
      const id = nextId.current++;
      setToasts((all) => [...all.slice(-2), { id, title, description, tone }]);
      window.setTimeout(() => dismiss(id), 4500);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-5 right-5 z-[100] flex w-[360px] max-w-[calc(100vw-2.5rem)] flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={cn(
              "pointer-events-auto flex items-start gap-3 rounded-lg border bg-popover px-4 py-3 text-sm shadow-lifted",
              "animate-in fade-in slide-in-from-bottom-2 duration-200",
            )}
          >
            {t.tone === "error" ? (
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            ) : (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-foreground" />
            )}
            <div className="min-w-0 flex-1">
              <p className="font-medium leading-5">{t.title}</p>
              {t.description && <p className="mt-0.5 break-words text-muted-foreground">{t.description}</p>}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              className="rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
              aria-label="Dismiss notification"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
