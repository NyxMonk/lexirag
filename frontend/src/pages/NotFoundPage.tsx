import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <p className="label-caps">404</p>
      <h1 className="display mt-3 text-[34px]">This page does not exist</h1>
      <p className="mt-2 text-sm text-muted-foreground">The link may be outdated, or the item was removed.</p>
      <Button variant="outline" className="mt-6" asChild>
        <Link to="/">Back to overview</Link>
      </Button>
    </div>
  );
}
