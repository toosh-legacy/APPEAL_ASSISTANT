import * as React from "react";

import { cn } from "@/lib/utils";

// shadcn/ui Card
const Card = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(({ className, ...props }, ref) => (
  <section ref={ref} className={cn("rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6", className)} {...props} />
));
Card.displayName = "Card";

const CardTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(({ className, ...props }, ref) => (
  <h2 ref={ref} className={cn("text-lg font-bold", className)} {...props} />
));
CardTitle.displayName = "CardTitle";

export { Card, CardTitle };
