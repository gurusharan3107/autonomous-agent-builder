/* eslint-disable react-refresh/only-export-components */
import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-[var(--radius-sm)] border border-transparent text-[13px] font-medium tracking-normal whitespace-nowrap transition-[background-color,color,border-color,box-shadow,filter,transform] duration-150 ease-out outline-none select-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-40 aria-invalid:border-destructive aria-invalid:ring-2 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-[var(--shadow-sm)] hover:brightness-110",
        outline:
          "border-[var(--line-strong)] bg-[var(--surface)] text-foreground hover:bg-[var(--surface-raised)] aria-expanded:bg-[var(--surface-raised)] aria-expanded:text-foreground",
        secondary:
          "border-[var(--line)] bg-[var(--surface-raised)] text-foreground shadow-[var(--shadow-sm)] hover:brightness-105 aria-expanded:bg-[var(--surface-raised)] aria-expanded:text-foreground",
        ghost:
          "text-foreground-2 hover:bg-[color-mix(in_oklab,var(--fg)_8%,transparent)] hover:text-foreground aria-expanded:bg-[color-mix(in_oklab,var(--fg)_8%,transparent)] aria-expanded:text-foreground",
        destructive:
          "bg-status-blocked text-primary-foreground hover:brightness-105 focus-visible:border-status-blocked/40 focus-visible:ring-status-blocked/20",
        danger:
          "bg-status-blocked text-primary-foreground hover:brightness-105 focus-visible:border-status-blocked/40 focus-visible:ring-status-blocked/20",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-8 gap-1.5 px-3 has-data-[icon=inline-end]:pr-2.5 has-data-[icon=inline-start]:pl-2.5",
        xs: "h-6 gap-1 px-2.5 text-[11px] has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 px-2.5 text-[12px] has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        lg: "h-10 gap-1.5 px-4 has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
        icon: "size-8",
        "icon-xs": "size-6 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
