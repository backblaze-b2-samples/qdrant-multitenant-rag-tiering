"use client";

import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTheme } from "next-themes";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { DEFAULT_THEME, THEME_OPTIONS, normalizeTheme } from "@/lib/theme-preference";
import { settingsSchema, type SettingsValues } from "@/lib/settings-schema";
import { useTieringPolicy } from "@/lib/queries";
import { IDLE_OPTIONS } from "@/lib/tenant-form";

function describeSeconds(seconds: number): string {
  const named = IDLE_OPTIONS.find((o) => o.seconds === seconds);
  return named ? named.label : `${seconds} s`;
}

/**
 * The tiering policy is SERVER configuration (environment variables read at
 * API start), so it is shown read-only: a browser-side toggle that did not
 * change what the sweep does would be a lie. Theme is the one real browser
 * preference.
 */
function PolicyCard() {
  const { data: policy, isLoading } = useTieringPolicy();
  const rows = policy
    ? [
        ["Idle threshold", describeSeconds(policy.idle_seconds), "TIERING_IDLE_SECONDS"],
        [
          "Background sweep",
          policy.sweep_interval_seconds === 0
            ? "disabled"
            : `every ${describeSeconds(policy.sweep_interval_seconds)}`,
          "TIERING_SWEEP_INTERVAL_SECONDS",
        ],
        ["Snapshot pruning", policy.prune_enabled ? "allowed" : "disabled", "SNAPSHOT_PRUNE_ENABLED"],
      ]
    : [];

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Tiering policy</CardTitle>
        <CardDescription className="text-xs">
          Read-only. Change it in the API environment and restart the API.
        </CardDescription>
      </CardHeader>
      <CardContent className="p-5">
        {isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : (
          <dl className="space-y-3 text-sm">
            {rows.map(([label, value, env]) => (
              <div key={env} className="grid grid-cols-[10rem_1fr] gap-3">
                <dt className="text-muted-foreground">{label}</dt>
                <dd>
                  <span className="font-medium">{value}</span>{" "}
                  <code className="ml-1 text-xs text-muted-foreground">{env}</code>
                </dd>
              </div>
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

export function SettingsForm() {
  const [submitting, setSubmitting] = useState(false);
  // next-themes owns the theme; the radio group is a view onto it, which is
  // why the header toggle and this form always agree.
  const { setTheme, theme } = useTheme();
  const hydratedRef = useRef(false);
  const form = useForm<SettingsValues>({
    resolver: zodResolver(settingsSchema),
    defaultValues: { theme: DEFAULT_THEME },
  });

  useEffect(() => {
    if (hydratedRef.current || theme === undefined) return;
    hydratedRef.current = true;
    form.reset({ theme: normalizeTheme(theme) });
  }, [form, theme]);

  const onSubmit = (values: SettingsValues) => {
    setSubmitting(true);
    setTheme(values.theme);
    setSubmitting(false);
    toast.success("Theme saved in this browser");
  };

  return (
    <div className="space-y-6">
      <PolicyCard />
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <Card>
            <CardHeader className="border-b border-border py-4 px-5">
              <CardTitle className="card-title">Appearance</CardTitle>
            </CardHeader>
            <CardContent className="p-5">
              <FormField
                control={form.control}
                name="theme"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Theme</FormLabel>
                    <FormControl>
                      <RadioGroup onValueChange={field.onChange} value={field.value} className="flex gap-6">
                        {THEME_OPTIONS.map((t) => (
                          <label key={t} className="flex items-center gap-2 text-sm capitalize cursor-pointer">
                            <RadioGroupItem value={t} />
                            {t}
                          </label>
                        ))}
                      </RadioGroup>
                    </FormControl>
                    <FormDescription>Applied when you save. The header toggle changes it too.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>
          <div className="flex justify-end">
            <Button type="submit" disabled={submitting}>
              Save theme
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
}
