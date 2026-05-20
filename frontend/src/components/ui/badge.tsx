/* eslint-disable react-refresh/only-export-components */
import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-[var(--radius-full)] border border-transparent px-2 py-0.5 text-[11px] font-medium whitespace-nowrap transition-all focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default: "border-[color:var(--status-active)] bg-[color:var(--status-active-soft)] text-status-active [a]:hover:brightness-105",
        secondary:
          "border-[var(--line)] bg-[var(--surface-raised)] text-foreground [a]:hover:brightness-105",
        destructive:
          "border-[color:var(--status-blocked)] bg-[color:var(--status-blocked-soft)] text-status-blocked focus-visible:ring-status-blocked/20 [a]:hover:brightness-105",
        outline:
          "border-[var(--line)] bg-[var(--surface)] text-foreground [a]:hover:bg-[var(--surface-raised)] [a]:hover:text-foreground",
        ghost:
          "text-foreground-3 hover:bg-[color-mix(in_oklab,var(--fg)_8%,transparent)] hover:text-foreground-2",
        link: "text-primary underline-offset-4 hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
