import type { LucideIcon } from "lucide-react";

interface SectionTitleProps {
  icon: LucideIcon;
  title: string;
  iconClassName: string;
}

export function SectionTitle({ icon: Icon, title, iconClassName }: SectionTitleProps) {
  return (
    <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
      <Icon className={`h-5 w-5 ${iconClassName}`} /> {title}
    </h2>
  );
}
