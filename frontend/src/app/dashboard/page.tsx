"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest, clearSession, getSelectedBusinessId, setSelectedBusinessId } from "@/lib/api";

type User = { id: string; email: string; full_name: string };
type Business = { id: string; name: string; role: "owner" | "admin" | "member" | "viewer" };

export default function DashboardPage() {
  const [user, setUser] = useState<User | null>(null);
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);

  const load = useCallback(async () => {
    try {
      const [profile, items] = await Promise.all([
        apiRequest<User>("/api/v1/users/me"),
        apiRequest<Business[]>("/api/v1/businesses"),
      ]);
      setUser(profile);
      setBusinesses(items);
      const saved = getSelectedBusinessId();
      const current = items.find((item) => item.id === saved)?.id ?? items[0]?.id ?? "";
      setSelectedId(current);
      if (current) setSelectedBusinessId(current);
    } catch (cause) {
      clearSession();
      window.location.assign("/login");
      setError(cause instanceof Error ? cause.message : "Please sign in again.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function createBusiness(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try {
      const created = await apiRequest<Business>("/api/v1/businesses", {
        method: "POST",
        body: JSON.stringify({ name: businessName }),
      });
      setBusinesses((current) => [...current, created]);
      setSelectedId(created.id);
      setSelectedBusinessId(created.id);
      setBusinessName("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Business could not be created.");
    }
  }

  if (busy) return <main className="mx-auto max-w-5xl p-8 text-slate-600">Loading workspace…</main>;

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-5 py-10 sm:px-8">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-800">LedgerPilot</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">Workspace</h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-600">{user?.full_name}</span>
          <Button variant="outline" size="sm" onClick={() => { clearSession(); window.location.assign("/login"); }}>
            Sign out
          </Button>
        </div>
      </header>

      {error && <p role="alert" className="mt-5 rounded-md bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}

      <section className="mt-8 grid gap-5 md:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle>Choose a business</CardTitle>
            <p className="text-sm text-slate-600">Your workspace is scoped to businesses where you are a member.</p>
          </CardHeader>
          <CardContent>
            {businesses.length ? (
              <label className="block space-y-2 text-sm font-medium">
                Active business
                <select
                  className="h-10 w-full rounded-md border border-slate-300 bg-white px-3"
                  value={selectedId}
                  onChange={(event) => { setSelectedId(event.target.value); setSelectedBusinessId(event.target.value); }}
                >
                  {businesses.map((business) => (
                    <option key={business.id} value={business.id}>{business.name} · {business.role}</option>
                  ))}
                </select>
              </label>
            ) : (
              <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-900">Create a business to establish your first isolated workspace.</p>
            )}
            {selectedId && <p className="mt-4 text-sm text-slate-600">Business selected for this tab.</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Create a business</CardTitle>
            <p className="text-sm text-slate-600">You’ll become its owner and can add registered users as members.</p>
          </CardHeader>
          <CardContent>
            <form className="space-y-3" onSubmit={createBusiness}>
              <label className="block space-y-1.5 text-sm font-medium">
                Business name
                <Input required maxLength={160} value={businessName} onChange={(e) => setBusinessName(e.target.value)} />
              </label>
              <Button type="submit">Create business</Button>
            </form>
          </CardContent>
        </Card>
      </section>

      <section className="mt-8 rounded-xl border border-dashed border-slate-300 bg-white p-8">
        <h2 className="text-lg font-semibold">Financial workspace</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
          Your account and business access are active. Statements and invoices will appear in the selected business workspace.
        </p>
        {selectedId && <Link className="mt-4 inline-block text-sm font-medium text-emerald-800 underline" href={`/businesses/${selectedId}/documents`}>Open business workspace</Link>}
      </section>
    </main>
  );
}
