import { useLocation } from "wouter";
import { Construction } from "lucide-react";
import { useTranslation } from "@/components/Layout";

export default function Placeholder() {
  const [location] = useLocation();
  const { t } = useTranslation();

  const pageName = location.replace("/", "") || "page";
  const navKey = `nav.${pageName}` as string;
  const title = t(navKey) !== navKey ? t(navKey) : pageName.charAt(0).toUpperCase() + pageName.slice(1);

  return (
    <div className="flex flex-col items-center justify-center py-32 text-center">
      <Construction className="w-16 h-16 text-muted-foreground/30 mb-4" strokeWidth={1.2} />
      <h2 className="text-xl font-serif font-bold mb-2">{title}</h2>
      <p className="text-sm text-muted-foreground max-w-sm">
        This page is a placeholder for the React prototype. The full implementation would replace your current Flask template.
      </p>
    </div>
  );
}
