"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest, clearSession, getSelectedBusinessId, setSelectedBusinessId } from "@/lib/api";

type User = { id: string; email: string; full_name: string };
type Business = { id: string; name: string; role: "owner" | "admin" | "member" | "viewer" };
type FinancialSummary = {
  total_transactions: number;
  matched_transactions: number;
  unmatched_transactions: number;
  exceptions: number;
  pending_approvals: number;
  investigations_in_progress: number;
  reconciliation_progress_percent: number;
};

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [summary, setSummary] = useState<FinancialSummary | null>(null);

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
      router.push("/login");
      setError(cause instanceof Error ? cause.message : "Please sign in again.");
    } finally {
      setBusy(false);
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selectedId) {
      setSummary(null);
      return;
    }
    void apiRequest<FinancialSummary>(`/api/v1/businesses/${selectedId}/reconciliation/summary`)
      .then(setSummary)
      .catch(() => setSummary(null));
  }, [selectedId]);

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

  if (busy) {
    return <main className="mx-auto max-w-7xl p-8 text-slate-600">Loading workspace...</main>;
  }

  const progress = Math.min(100, Math.max(0, summary?.reconciliation_progress_percent ?? 0));
  const total = summary?.total_transactions ?? 0;
  const matchedShare = total ? Math.min(100, ((summary?.matched_transactions ?? 0) / total) * 100) : 0;
  const unmatchedShare = total
    ? Math.min(100 - matchedShare, ((summary?.unmatched_transactions ?? 0) / total) * 100)
    : 0;

  const metrics = summary
    ? [
        ["Transactions", summary.total_transactions, "Records in this business"],
        ["Matched", summary.matched_transactions, "Reviewed and allocated"],
        ["Unmatched", summary.unmatched_transactions, "Need a closer look"],
        ["Open exceptions", summary.exceptions, "Investigation queue"],
        ["Pending approvals", summary.pending_approvals, "Waiting for your review"],
        ["Investigating", summary.investigations_in_progress, "Active investigations"],
      ]
    : [];

  return (
    <main className="mx-auto min-h-screen max-w-[1440px] px-5 py-7 sm:px-8 lg:px-10">
      <header className="flex flex-wrap items-center justify-between gap-5 border-b border-slate-300 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl border border-gold-600/50 bg-gold-400/10 text-sm font-semibold tracking-tight text-gold-400">
              LP
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-gold-400">LedgerPilot</p>
              <h1 className="mt-0.5 text-2xl font-semibold tracking-tight sm:text-3xl">
                Financial overview
              </h1>
            </div>
          </div>
          <p className="mt-3 text-sm text-slate-600">
            A clear view of your reconciliation activity and review queue.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden text-right sm:block">
            <span className="block text-xs text-slate-500">Signed in as</span>
            <span className="text-sm text-slate-800">{user?.full_name}</span>
          </span>
          <Button variant="outline" size="sm" onClick={() => { clearSession(); router.push("/login"); }}>
            Sign out
          </Button>
        </div>
      </header>

      {error && <p role="alert" className="mt-5 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}

      <section className="mt-7 flex flex-wrap items-end justify-between gap-5">
        <div className="w-full max-w-md">
          <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
            Active business
          </label>
          {businesses.length ? (
            <select
              aria-label="Active business"
              className="h-11 w-full rounded-lg border border-slate-300 bg-elevated px-3 text-sm text-slate-900 outline-none focus:border-gold-400 focus:ring-2 focus:ring-gold-400/30"
              value={selectedId}
              onChange={(event) => {
                setSelectedId(event.target.value);
                setSelectedBusinessId(event.target.value);
              }}
            >
              {businesses.map((business) => (
                <option key={business.id} value={business.id}>
                  {business.name} · {business.role}
                </option>
              ))}
            </select>
          ) : (
            <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              Create a business to establish your first isolated workspace.
            </p>
          )}
          {selectedId && <p className="mt-2 text-xs text-slate-500">Business data is scoped to your membership.</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {selectedId && (
            <>
              <Link href={`/businesses/${selectedId}/documents`} className="inline-flex h-10 items-center rounded-lg border border-slate-300 px-4 text-sm text-slate-700 transition-colors hover:border-gold-600 hover:bg-elevated">
                Documents
              </Link>
              <Link href={`/businesses/${selectedId}/reconciliation`} className="inline-flex h-10 items-center rounded-lg bg-gold-400 px-4 text-sm font-medium text-[#101010] shadow-[0_4px_16px_rgba(198,167,107,0.14)] transition-colors hover:bg-gold-300">
                Open reconciliation
              </Link>
            </>
          )}
        </div>
      </section>

      <section className="mt-8">
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-gold-400">At a glance</p>
            <h2 className="mt-1 text-xl font-semibold">Reconciliation health</h2>
          </div>
          {summary && <span className="text-xs text-slate-500">Current business · live totals</span>}
        </div>
        {summary ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            {metrics.map(([label, value, note], index) => (
              <Card key={label} className={index === 1 ? "border-gold-600/60" : ""}>
                <CardContent className="p-5">
                  <p className="text-xs font-medium uppercase tracking-[0.1em] text-slate-500">{label}</p>
                  <p className={`mt-3 text-3xl font-semibold tracking-tight ${index === 1 ? "text-gold-400" : "text-slate-900"}`}>
                    {value}
                  </p>
                  <p className="mt-2 text-xs text-slate-500">{note}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="p-6">
              <p className="text-sm text-slate-600">Verify imported records to prepare your first reconciliation run.</p>
            </CardContent>
          </Card>
        )}
      </section>

      {summary && (
        <section className="mt-5 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <Card>
            <CardContent className="flex flex-wrap items-center gap-6 p-6 sm:gap-9">
              <div
                className="relative grid h-36 w-36 shrink-0 place-items-center rounded-full"
                style={{ background: `conic-gradient(#C6A76B ${progress}%, #33302A ${progress}% 100%)` }}
                role="img"
                aria-label={`${progress}% reconciliation progress`}
              >
                <div className="grid h-28 w-28 place-content-center rounded-full border border-slate-300 bg-surface text-center">
                  <span className="text-3xl font-semibold text-slate-900">{progress}%</span>
                  <span className="mt-1 text-[10px] uppercase tracking-[0.12em] text-slate-500">Reconciled</span>
                </div>
              </div>
              <div className="min-w-[12rem] flex-1">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gold-400">Progress</p>
                <h3 className="mt-1 text-lg font-semibold">Review with confidence</h3>
                <p className="mt-2 max-w-md text-sm leading-6 text-slate-600">
                  Matches remain proposals until approved. Balances update only after an authorized review.
                </p>
                {selectedId && <Link href={`/businesses/${selectedId}/reconciliation`} className="mt-4 inline-flex text-sm font-medium text-gold-400 underline-offset-4 hover:underline">Review proposals <span aria-hidden="true" className="ml-2">→</span></Link>}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-6">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Transaction mix</p>
                  <h3 className="mt-1 text-lg font-semibold">Matching status</h3>
                </div>
                <span className="rounded-full border border-slate-300 px-2.5 py-1 text-xs text-slate-500">{total} total</span>
              </div>
              <div className="mt-6 h-3 overflow-hidden rounded-full bg-elevated" role="img" aria-label={`${summary.matched_transactions} matched and ${summary.unmatched_transactions} unmatched transactions`}>
                <div className="flex h-full w-full">
                  <span className="h-full bg-emerald-800" style={{ width: `${matchedShare}%` }} />
                  <span className="h-full bg-bronze" style={{ width: `${unmatchedShare}%` }} />
                </div>
              </div>
              <div className="mt-5 grid grid-cols-2 gap-4">
                <div className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-emerald-800" /><div><p className="text-xs text-slate-500">Matched</p><p className="mt-0.5 text-lg font-semibold">{summary.matched_transactions}</p></div></div>
                <div className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-bronze" /><div><p className="text-xs text-slate-500">Unmatched</p><p className="mt-0.5 text-lg font-semibold">{summary.unmatched_transactions}</p></div></div>
              </div>
            </CardContent>
          </Card>
        </section>
      )}

      <section className="mt-5 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Create a business</CardTitle>
            <p className="text-sm text-slate-600">You become its owner and can add registered users as members.</p>
          </CardHeader>
          <CardContent>
            <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={createBusiness}>
              <label className="block flex-1 space-y-1.5 text-sm font-medium">
                Business name
                <Input required maxLength={160} value={businessName} onChange={(event) => setBusinessName(event.target.value)} />
              </label>
              <Button type="submit">Create business</Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Review queue</CardTitle>
            <p className="text-sm text-slate-600">Keep proposals and exceptions moving with a clear evidence trail.</p>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-3">
            <div className="rounded-xl border border-slate-300 bg-elevated px-4 py-3"><p className="text-xs text-slate-500">Awaiting approval</p><p className="mt-1 text-xl font-semibold text-gold-400">{summary?.pending_approvals ?? 0}</p></div>
            <div className="rounded-xl border border-slate-300 bg-elevated px-4 py-3"><p className="text-xs text-slate-500">Open exceptions</p><p className="mt-1 text-xl font-semibold">{summary?.exceptions ?? 0}</p></div>
            {!selectedId && <p className="self-center text-sm text-slate-600">Create or select a business to view its review queue.</p>}
          </CardContent>
        </Card>
      </section>
    </main>
  );
}
