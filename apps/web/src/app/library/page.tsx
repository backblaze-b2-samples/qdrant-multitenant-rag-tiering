import { Suspense } from "react";

import { LibraryBrowser } from "@/components/library/library-browser";
import { Skeleton } from "@/components/ui/skeleton";

export default function LibraryPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Library</h1>
        <p className="mt-1.5 max-w-prose text-sm text-muted-foreground">
          Everything this app wrote to B2: each tenant&apos;s corpus, its collection
          snapshots and latest.json manifest, and the latency reports. Click an object
          to preview it in the bucket explorer.
        </p>
      </div>
      <Suspense fallback={<Skeleton className="h-48 w-full" />}>
        <LibraryBrowser />
      </Suspense>
    </div>
  );
}
