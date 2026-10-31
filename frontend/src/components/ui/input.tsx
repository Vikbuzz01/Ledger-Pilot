import type { InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "flex h-10 w-full rounded-lg border border-slate-300 bg-elevated px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-500 focus-visible:border-gold-400 focus-visible:ring-2 focus-visible:ring-gold-400/40 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
