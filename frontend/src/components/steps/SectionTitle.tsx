import type { LucideIcon } from "lucide-react";

import { HelpTip } from "@/components/ui/help-tip";

interface SectionTitleProps {
  icon: LucideIcon;
  title: string;
  iconClassName: string;
  help?: string;
}

export function SectionTitle({ icon: Icon, title, iconClassName, help }: SectionTitleProps) {
  return (
    <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
      <Icon className={`h-5 w-5 ${iconClassName}`} /> {title}
      <HelpTip text={help} />
    </h2>
  );
}
