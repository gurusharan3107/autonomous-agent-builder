import type { HTMLAttributes, ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  BrandMark,
  EmptyState,
  Eyebrow,
  Kbd,
  Meter,
  SectionLabel,
  StatusDot,
  StatusPill,
  StatPill,
  StatPill as Stat,
  SurfacePanel as Surface,
  Tabs,
  type TabsItem,
} from "@/components/workspace";
import { cn } from "@/lib/utils";

function Code({ children, className, ...props }: HTMLAttributes<HTMLElement> & { children: ReactNode }) {
  return (
    <code
      className={cn(
        "rounded-[var(--radius-xs)] border border-[var(--line)] bg-[var(--surface-raised)] px-1.5 py-0.5 font-mono text-[0.86em] text-foreground",
        className,
      )}
      {...props}
    >
      {children}
    </code>
  );
}

export {
  BrandMark,
  Button,
  Code,
  EmptyState,
  Eyebrow,
  Input,
  Kbd,
  Meter,
  SectionLabel,
  Stat,
  StatPill,
  StatusDot,
  StatusPill,
  Surface,
  Tabs,
  type TabsItem,
};
