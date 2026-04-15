import { Link } from "wouter";
import { AlertCircle, ArrowRight } from "lucide-react";

export default function FeatureUnavailable({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center justify-center gap-4 py-24 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400">
        <AlertCircle className="h-7 w-7" />
      </div>
      <div className="space-y-2">
        <h1 className="text-2xl font-serif font-bold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
        <Link href="/">
          <span className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
            Go to dashboard <ArrowRight className="h-4 w-4" />
          </span>
        </Link>
        <Link href="/database">
          <span className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted">
            Open database
          </span>
        </Link>
      </div>
    </div>
  );
}
