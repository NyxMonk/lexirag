import { Loader2 } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateWorkspace } from "@/hooks/queries";
import { useToast } from "@/hooks/useToast";

export function CreateWorkspaceDialog({
  trigger,
  open: controlledOpen,
  onOpenChange,
  navigateOnCreate = true,
}: {
  trigger?: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  navigateOnCreate?: boolean;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const create = useCreateWorkspace();
  const navigate = useNavigate();
  const { toast } = useToast();

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setName("");
      setDescription("");
      create.reset();
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const workspace = await create.mutateAsync({ name: name.trim(), description: description.trim() || null });
      handleOpenChange(false);
      toast({ title: "Workspace created", description: workspace.name });
      if (navigateOnCreate) navigate(`/workspaces/${workspace.id}`);
    } catch {
      /* error rendered below */
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New workspace</DialogTitle>
          <DialogDescription>
            Group the documents for a matter, client or area of law. Questions are answered within a workspace.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="grid gap-5">
          <div className="grid gap-2">
            <Label htmlFor="ws-name">Name</Label>
            <Input
              id="ws-name"
              autoFocus
              maxLength={120}
              placeholder="e.g. Tenancy dispute — Pune"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="ws-desc">
              Description <span className="font-normal text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id="ws-desc"
              maxLength={2000}
              rows={3}
              placeholder="What is this workspace for?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          {create.error && (
            <p role="alert" className="text-sm text-destructive">
              {create.error.message}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              {create.isPending && <Loader2 className="animate-spin" />}
              Create workspace
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
