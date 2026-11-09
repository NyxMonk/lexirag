import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const fieldBase =
  "w-full rounded-md border border-input bg-surface px-3 text-sm shadow-subtle transition-colors placeholder:text-muted-foreground/70 hover:border-foreground/20 focus-visible:border-foreground/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/15 disabled:cursor-not-allowed disabled:opacity-50";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input type={type} className={cn(fieldBase, "h-9 py-1", className)} ref={ref} {...props} />
  ),
);
Input.displayName = "Input";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea className={cn(fieldBase, "min-h-[80px] resize-none py-2", className)} ref={ref} {...props} />
  ),
);
Textarea.displayName = "Textarea";
