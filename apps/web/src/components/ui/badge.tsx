import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// shadcn/ui Badge
const badgeVariants = cva("inline-flex items-center rounded-full px-2.5 py-0.5 text-sm font-medium", {
  variants: {
    variant: {
      default: "bg-brand-light text-brand-dark",
      warning: "bg-amber-100 text-amber-900",
      success: "bg-green-100 text-green-900",
    },
  },
  defaultVariants: { variant: "default" },
});

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
