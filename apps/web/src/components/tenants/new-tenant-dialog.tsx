"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

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
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { useCreateTenant, useTenantProgress } from "@/lib/queries";
import { tenantFormSchema, type TenantFormValues } from "@/lib/tenant-form";
import { createProgress } from "@/lib/tenant-state";
import { ACCEPTED_EXTENSIONS, documentProblems, readDocuments } from "@/lib/text-documents";

export function NewTenantDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const create = useCreateTenant();
  // Polled every half second while the create runs: stage, n of N, a bar.
  const creatingId = create.isPending ? (create.variables?.tenant_id ?? "") : "";
  const { data: progress } = useTenantProgress(creatingId, { enabled: !!creatingId });
  const current = progress?.tenant_id === creatingId ? progress : undefined;
  // Once the server reported a stage, an idle reply means indexing is done.
  const [startedFor, setStartedFor] = useState<string | null>(null);
  if (current?.state && startedFor !== creatingId) setStartedFor(creatingId);
  const stage = creatingId ? createProgress(current, startedFor === creatingId) : null;
  const form = useForm<TenantFormValues>({
    resolver: zodResolver(tenantFormSchema),
    defaultValues: { tenant_id: "", display_name: "" },
  });

  const onSubmit = async (values: TenantFormValues) => {
    const problems = files.length === 0 ? ["Pick at least one .txt or .md file."] : documentProblems(files);
    if (problems.length > 0) {
      setFileError(problems.join(" "));
      return;
    }
    setFileError(null);
    const documents = await readDocuments(files);
    create.mutate(
      { ...values, documents },
      {
        onSuccess: (tenant) => {
          toast.success(`Tenant ${tenant.tenant_id} is hot`, {
            description: `${tenant.document_count} document(s) in B2, ${tenant.point_count} points in Qdrant.`,
          });
          setOpen(false);
          form.reset();
          setFiles([]);
          router.push(`/tenants/${tenant.tenant_id}`);
        },
        onError: (error) => toast.error("Could not create the tenant", { description: error.message }),
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="h-8">
          <Plus aria-hidden="true" className="h-3.5 w-3.5" />
          New tenant
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New tenant</DialogTitle>
          <DialogDescription>
            Documents are written to B2 under the tenant&apos;s corpus prefix, then
            chunked and embedded into its own Qdrant collection.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="tenant_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Tenant id</FormLabel>
                  <FormControl>
                    <Input placeholder="acme-legal" autoComplete="off" {...field} />
                  </FormControl>
                  <FormDescription>
                    lowercase letters, digits and hyphens, 2 to 40 characters
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="display_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Display name</FormLabel>
                  <FormControl>
                    <Input placeholder="Acme Legal" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="space-y-2">
              <Label htmlFor="new-tenant-documents">Documents</Label>
              <Input
                id="new-tenant-documents"
                type="file"
                multiple
                accept={ACCEPTED_EXTENSIONS.join(",")}
                onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
              />
              <p className="text-sm text-muted-foreground">
                Two to twenty short text files is enough for a test run; or use Seed
                demo tenants
              </p>
              {fileError && (
                <p className="text-sm text-destructive" role="alert">
                  {fileError}
                </p>
              )}
            </div>
            {create.isPending && (
              <div className="space-y-2" data-testid="create-progress">
                <Progress value={stage?.percent ?? 100} aria-label="Create progress" />
                <p className="text-sm text-muted-foreground" aria-live="polite" data-testid="create-stage">
                  {stage?.text ?? "Indexed; loading the new tenant…"}
                </p>
              </div>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />}
                {create.isPending ? "Indexing…" : "Create tenant"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
