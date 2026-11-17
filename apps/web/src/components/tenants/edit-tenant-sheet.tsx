"use client";

import { useState } from "react";
import { Loader2, Pencil } from "lucide-react";
import { toast } from "sonner";
import type { TenantDetail } from "@qdrant-multitenant-rag-tiering/shared";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useUpdateTenant } from "@/lib/queries";
import { ACCEPTED_EXTENSIONS, documentProblems, readDocuments } from "@/lib/text-documents";

/** Edit name and documents. A parked tenant is restored first, server-side. */
export function EditTenantSheet({ tenant }: { tenant: TenantDetail }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(tenant.display_name);
  const [remove, setRemove] = useState<string[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const update = useUpdateTenant(tenant.tenant_id);

  const reset = (next: boolean) => {
    setOpen(next);
    if (next) {
      setName(tenant.display_name);
      setRemove([]);
      setFiles([]);
      setProblem(null);
    }
  };

  const save = async () => {
    const problems = documentProblems(files);
    if (!name.trim()) problems.push("Display name is required.");
    if (problems.length) {
      setProblem(problems.join(" "));
      return;
    }
    const add_documents = await readDocuments(files);
    update.mutate(
      {
        display_name: name.trim() === tenant.display_name ? null : name.trim(),
        remove_documents: remove,
        add_documents,
      },
      {
        onSuccess: () => {
          toast.success("Tenant updated", {
            description: add_documents.length || remove.length ? "Changed documents re-embedded; the B2 snapshot is now stale until the next park." : undefined,
          });
          setOpen(false);
        },
        onError: (error) => setProblem(error.message),
      }
    );
  };

  return (
    <Sheet open={open} onOpenChange={reset}>
      <SheetTrigger asChild>
        <Button size="sm" variant="outline" className="h-8">
          <Pencil aria-hidden="true" className="h-3.5 w-3.5" />
          Edit
        </Button>
      </SheetTrigger>
      <SheetContent className="overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Edit {tenant.tenant_id}</SheetTitle>
          <SheetDescription>
            {tenant.state === "parked"
              ? "This tenant is parked: saving document changes restores it from B2 first."
              : "Document changes are written to B2 and re-embedded."}
          </SheetDescription>
        </SheetHeader>
        <div className="space-y-5 px-4">
          <div className="space-y-2">
            <Label htmlFor="edit-name">Display name</Label>
            <Input id="edit-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Remove documents</legend>
            {tenant.documents.map((doc) => (
              <label key={doc.filename} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={remove.includes(doc.filename)}
                  onCheckedChange={(checked) =>
                    setRemove((prev) =>
                      checked ? [...prev, doc.filename] : prev.filter((n) => n !== doc.filename)
                    )
                  }
                />
                <span className="font-mono text-xs">{doc.filename}</span>
              </label>
            ))}
          </fieldset>
          <div className="space-y-2">
            <Label htmlFor="edit-add">Add documents</Label>
            <Input
              id="edit-add"
              type="file"
              multiple
              accept={ACCEPTED_EXTENSIONS.join(",")}
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            <p className="text-xs text-muted-foreground">
              .txt or .md; a file with an existing name replaces that document.
            </p>
          </div>
          {problem && (
            <p className="text-sm text-destructive" role="alert">
              {problem}
            </p>
          )}
        </div>
        <SheetFooter>
          <Button onClick={save} disabled={update.isPending}>
            {update.isPending && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />}
            Save changes
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
