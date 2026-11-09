import { useEffect, useState, type ReactNode } from "react";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { UploadPanel } from "@/features/documents/UploadPanel";
import { useWorkspaces } from "@/hooks/queries";

/** Upload entry point for places that are not scoped to a workspace (dashboard, documents). */
export function UploadDialog({
  trigger,
  open,
  onOpenChange,
}: {
  trigger?: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const workspaces = useWorkspaces();
  const [workspaceId, setWorkspaceId] = useState<string>("");

  useEffect(() => {
    if (!workspaceId && workspaces.data?.length) setWorkspaceId(workspaces.data[0].id);
  }, [workspaces.data, workspaceId]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Upload documents</DialogTitle>
          <DialogDescription>PDF files are stored locally and attached to a workspace.</DialogDescription>
        </DialogHeader>
        {workspaces.data && workspaces.data.length === 0 ? (
          <p className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
            Create a workspace first — every document belongs to one.
          </p>
        ) : (
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="upload-ws">Workspace</Label>
              <Select value={workspaceId} onValueChange={setWorkspaceId}>
                <SelectTrigger id="upload-ws">
                  <SelectValue placeholder="Select a workspace" />
                </SelectTrigger>
                <SelectContent>
                  {workspaces.data?.map((w) => (
                    <SelectItem key={w.id} value={w.id}>
                      {w.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {workspaceId && <UploadPanel key={workspaceId} workspaceId={workspaceId} />}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
