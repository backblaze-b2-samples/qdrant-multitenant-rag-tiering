"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useDeleteTenant } from "@/lib/queries";

export function DeleteTenant({ tenantId }: { tenantId: string }) {
  const router = useRouter();
  const [typed, setTyped] = useState("");
  const remove = useDeleteTenant(tenantId);

  const confirm = () =>
    remove.mutate(typed, {
      onSuccess: (result) => {
        toast.success(`Deleted ${tenantId}`, {
          description: `${result.deleted_keys.length} object(s) removed from B2${result.collection_dropped ? "; collection dropped" : ""}. Reports were kept.`,
        });
        router.push("/tenants");
      },
      onError: (error) => toast.error("Delete failed", { description: error.message }),
    });

  return (
    <Card className="border-destructive/40">
      <CardHeader className="border-b border-destructive/30 py-4 px-5">
        <CardTitle className="card-title text-destructive">Danger zone</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
        <div>
          <p className="text-sm font-medium">Delete this tenant</p>
          <p className="text-xs text-muted-foreground">
            Drops its collection and deletes only its corpus and snapshot objects in B2.
            Latency reports are kept.
          </p>
        </div>
        <AlertDialog onOpenChange={() => setTyped("")}>
          <AlertDialogTrigger asChild>
            <Button variant="outline" size="sm" className="text-destructive">
              Delete tenant
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete {tenantId}?</AlertDialogTitle>
              <AlertDialogDescription>
                This permanently deletes the tenant&apos;s documents and every snapshot under
                its prefix. Type the tenant id to confirm.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <div className="space-y-2">
              <Label htmlFor="confirm-delete">Tenant id</Label>
              <Input
                id="confirm-delete"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder={tenantId}
                autoComplete="off"
              />
            </div>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                disabled={typed !== tenantId || remove.isPending}
                onClick={confirm}
                className={buttonVariants({ variant: "destructive" })}
              >
                Delete permanently
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  );
}
