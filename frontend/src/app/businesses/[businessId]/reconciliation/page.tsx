"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiRequest } from "@/lib/api";

type Summary = {
  run_id: string | null; total_transactions: number; matched_transactions: number;
  unmatched_transactions: number; exceptions: number; pending_approvals: number;
  investigations_in_progress: number; invoices: number; reconciliation_progress_percent: number;
};
type Run = { id: string; status: string; created_at: string };
type Candidate = {
  id: string; transaction_id: string | null; invoice_id: string | null;
  matching_method: string; scoring_factors: Record<string, string | number | boolean | null>;
  confidence_score: string; status: string; rationale: string;
  amounts_compared: { transactions: string[]; invoice: string; currency: string };
  evidence: {
    transaction_ids: string[]; invoice_id: string; transaction_sources: string[]; invoice_source: string;
    invoice_reference: string | null; invoice_vendor: string | null;
    transaction_references: (string | null)[]; transaction_descriptions: (string | null)[];
  };
};
type ExceptionRow = {
  id: string; exception_type: string; transaction_ids: string[]; invoice_ids: string[];
  summary: string; status: string; candidate_id: string | null;
};
type Finding = { statement: string; source_record_ids: string[] };
type Investigation = {
  id: string; status: string; report: null | {
    summary: string; verified_facts: Finding[]; supporting_evidence: Finding[];
    hypotheses: Finding[]; contradicting_evidence: Finding[]; missing_information: string[];
    confidence: string; recommended_resolution: string; human_review_required: boolean;
  };
};
type AliasCandidate = { id: string; normalized_name: string; candidate_name: string; evidence: unknown[]; verified: boolean };
type Audit = { id: string; action: string; entity_type: string; entity_id: string; reason: string | null; created_at: string };
type InvoiceBalance = { invoice_id: string; invoice_number: string | null; vendor_name: string | null; currency: string | null; total_amount: string; paid_amount: string; outstanding_amount: string };

export default function ReconciliationPage({ params }: { params: Promise<{ businessId: string }> }) {
  const [businessId, setBusinessId] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [exceptions, setExceptions] = useState<ExceptionRow[]>([]);
  const [aliases, setAliases] = useState<AliasCandidate[]>([]);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [balances, setBalances] = useState<InvoiceBalance[]>([]);
  const [investigations, setInvestigations] = useState<Record<string, Investigation>>({});
  const [filter, setFilter] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { void params.then((value) => setBusinessId(value.businessId)); }, [params]);

  const refresh = useCallback(async (id: string) => {
    if (!id) return;
    try {
      const [stats, runRows, aliasRows, auditRows, balanceRows] = await Promise.all([
        apiRequest<Summary>(`/api/v1/businesses/${id}/reconciliation/summary`),
        apiRequest<Run[]>(`/api/v1/businesses/${id}/reconciliation/runs`),
        apiRequest<AliasCandidate[]>(`/api/v1/businesses/${id}/reconciliation/aliases`),
        apiRequest<Audit[]>(`/api/v1/businesses/${id}/reconciliation/audit`),
        apiRequest<InvoiceBalance[]>(`/api/v1/businesses/${id}/reconciliation/invoice-balances`),
      ]);
      setSummary(stats); setRuns(runRows); setAliases(aliasRows); setAudit(auditRows); setBalances(balanceRows);
      const latest = runRows[0];
      if (latest) {
        const [candidateRows, exceptionRows] = await Promise.all([
          apiRequest<Candidate[]>(`/api/v1/businesses/${id}/reconciliation/runs/${latest.id}/candidates`),
          apiRequest<ExceptionRow[]>(`/api/v1/businesses/${id}/reconciliation/runs/${latest.id}/exceptions`),
        ]);
        setCandidates(candidateRows); setExceptions(exceptionRows);
      } else { setCandidates([]); setExceptions([]); }
      setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load reconciliation data."); }
  }, []);

  useEffect(() => { if (businessId) void refresh(businessId); }, [businessId, refresh]);

  async function startRun() {
    setBusy(true); setError("");
    try {
      await apiRequest(`/api/v1/businesses/${businessId}/reconciliation/runs`, {
        method: "POST", body: JSON.stringify({ idempotency_key: crypto.randomUUID() }),
      });
      await refresh(businessId);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Run could not start."); }
    finally { setBusy(false); }
  }

  async function decide(candidate: Candidate, decision: "approve" | "reject" | "request_information") {
    if (decision === "approve" && !window.confirm("This will allocate transaction amounts to the invoice. Continue?")) return;
    setBusy(true);
    try {
      await apiRequest(`/api/v1/businesses/${businessId}/reconciliation/candidates/${candidate.id}/decision`, {
        method: "POST", body: JSON.stringify({ decision, reason: reason || null }),
      });
      await refresh(businessId);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Review decision failed."); }
    finally { setBusy(false); }
  }

  async function investigate(exception: ExceptionRow) {
    setBusy(true);
    try {
      const result = await apiRequest<Investigation>(
        `/api/v1/businesses/${businessId}/reconciliation/exceptions/${exception.id}/investigations`,
        { method: "POST" },
      );
      setInvestigations((current) => ({ ...current, [exception.id]: result }));
      await refresh(businessId);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Investigation failed."); }
    finally { setBusy(false); }
  }

  async function reviewInvestigation(item: Investigation, decision: "approve" | "reject" | "request_information") {
    setBusy(true);
    try {
      await apiRequest(`/api/v1/businesses/${businessId}/reconciliation/investigations/${item.id}/decision`, {
        method: "POST", body: JSON.stringify({ decision, reason: reason || null }),
      });
      await refresh(businessId);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Review failed."); }
    finally { setBusy(false); }
  }

  async function resolveException(item: ExceptionRow) {
    if (!reason.trim()) { setError("Enter a reviewer note before resolving an exception."); return; }
    if (!window.confirm("Mark this exception resolved with the provided reviewer note?")) return;
    setBusy(true);
    try {
      await apiRequest(`/api/v1/businesses/${businessId}/reconciliation/exceptions/${item.id}/resolve`, {
        method: "POST", body: JSON.stringify({ reason }),
      });
      await refresh(businessId);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Resolution failed."); }
    finally { setBusy(false); }
  }

  async function verifyAlias(alias: AliasCandidate) {
    if (!window.confirm(`Verify “${alias.candidate_name}” as an alias for ${alias.normalized_name}?`)) return;
    try {
      await apiRequest(`/api/v1/businesses/${businessId}/reconciliation/aliases/${alias.id}/verify`, { method: "POST" });
      await refresh(businessId);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Alias verification failed."); }
  }

  const query = filter.trim().toLowerCase();
  const shownCandidates = candidates.filter((item) => `${item.matching_method} ${item.rationale} ${item.status}`.toLowerCase().includes(query));
  const shownExceptions = exceptions.filter((item) => `${item.exception_type} ${item.summary} ${item.status}`.toLowerCase().includes(query));

  if (!businessId) return <main className="p-8 text-slate-600">Loading reconciliation…</main>;
  return (
    <main className="mx-auto min-h-screen max-w-7xl px-5 py-8 sm:px-8">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div><Link href="/dashboard" className="text-sm text-emerald-800 underline">← Workspace</Link>
          <h1 className="mt-2 text-3xl font-semibold">Reconciliation review</h1>
          <p className="mt-1 text-sm text-slate-600">Deterministic proposals remain unconfirmed until a reviewer approves them.</p>
        </div>
        <Button onClick={startRun} disabled={busy}>{busy ? "Working…" : "Run reconciliation"}</Button>
      </header>
      {error && <p role="alert" className="mt-5 rounded-md bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
      <section className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        {[["Transactions", summary?.total_transactions], ["Matched", summary?.matched_transactions],
          ["Unmatched", summary?.unmatched_transactions], ["Open exceptions", summary?.exceptions],
          ["Pending review", summary?.pending_approvals], ["Invoices", summary?.invoices]].map(([label, value]) =>
          <Card key={label}><CardContent className="p-4"><p className="text-xs text-slate-500">{label}</p><p className="mt-1 text-2xl font-semibold">{value ?? "—"}</p></CardContent></Card>)}
      </section>
      <p className="mt-3 text-sm text-slate-600">Approved reconciliation progress: <strong>{summary?.reconciliation_progress_percent ?? 0}%</strong></p>
      <div className="mt-6 flex flex-wrap gap-3">
        <input aria-label="Filter reconciliation" className="h-10 min-w-64 rounded-md border border-slate-300 px-3 text-sm" placeholder="Filter proposals and exceptions" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <input aria-label="Reviewer note" className="h-10 min-w-64 flex-1 rounded-md border border-slate-300 px-3 text-sm" placeholder="Reviewer note for decisions" value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Card><CardHeader><CardTitle>Proposed matches</CardTitle><p className="text-sm text-slate-600">{runs[0] ? `Latest run ${runs[0].id}` : "Run reconciliation after verifying imported records."}</p></CardHeader>
          <CardContent className="space-y-3">
            {!shownCandidates.length && <p className="rounded-md bg-slate-50 p-4 text-sm text-slate-600">No matching candidates for this run or filter.</p>}
            {shownCandidates.map((item) => <article key={item.id} className="rounded-lg border border-slate-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2"><strong className="capitalize">{item.matching_method.replaceAll("_", " ")}</strong>
                <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-900">{item.status} · {Math.round(Number(item.confidence_score) * 100)}% confidence</span></div>
              <p className="mt-2 text-sm text-slate-700">{item.rationale}</p>
              <p className="mt-2 text-xs text-slate-500">Compared {item.amounts_compared.transactions.join(" + ")} {item.amounts_compared.currency} to invoice {item.amounts_compared.invoice} · {item.evidence.invoice_reference || item.invoice_id} · {item.evidence.invoice_vendor || "Vendor not recorded"}</p>
              <p className="mt-1 break-all text-xs text-slate-400">Source transactions: {item.evidence.transaction_ids.join(", ")}</p>
              {item.status === "proposed" && <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" disabled={busy} onClick={() => void decide(item, "approve")}>Approve allocation</Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => void decide(item, "reject")}>Reject</Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => void decide(item, "request_information")}>Request information</Button>
              </div>}
            </article>)}
          </CardContent>
        </Card>
        <Card><CardHeader><CardTitle>Exceptions</CardTitle><p className="text-sm text-slate-600">Investigate evidence or record a manual reviewer resolution.</p></CardHeader>
          <CardContent className="space-y-3">
            {!shownExceptions.length && <p className="rounded-md bg-slate-50 p-4 text-sm text-slate-600">No exceptions for this run or filter.</p>}
            {shownExceptions.map((item) => { const investigation = investigations[item.id]; const report = investigation?.report;
              return <article key={item.id} className="rounded-lg border border-slate-200 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2"><strong className="capitalize">{item.exception_type.replaceAll("_", " ")}</strong><span className="text-xs text-slate-500">{item.status}</span></div>
                <p className="mt-2 text-sm text-slate-700">{item.summary}</p>
                <p className="mt-1 break-all text-xs text-slate-400">Transactions: {item.transaction_ids.join(", ") || "none"} · Invoices: {item.invoice_ids.join(", ") || "none"}</p>
                {!investigation && item.status === "open" && <Button className="mt-3" size="sm" variant="outline" disabled={busy} onClick={() => void investigate(item)}>Investigate with AI</Button>}
                {investigation?.status === "unavailable" && <p className="mt-3 rounded-md bg-blue-50 p-3 text-sm text-blue-900">AI investigation unavailable. Configure AI_PROVIDER and AI_API_KEY; no report was fabricated.</p>}
                {investigation?.status === "failed" && <p className="mt-3 rounded-md bg-rose-50 p-3 text-sm text-rose-900">Investigation failed validation or provider execution. No report was stored.</p>}
                {report && <div className="mt-3 space-y-3 rounded-md bg-slate-50 p-3 text-sm">
                  <p className="font-medium">{report.summary}</p><p>Confidence: <strong>{report.confidence}</strong> · Human review required</p>
                  {([["Verified facts", report.verified_facts], ["Supporting evidence", report.supporting_evidence],
                    ["Hypotheses", report.hypotheses], ["Contradicting evidence", report.contradicting_evidence]] as [string, Finding[]][]).map(([title, findings]) =>
                    <div key={title}><h3 className="font-semibold">{title}</h3>{findings.length ? findings.map((f, i) => <p key={i} className="mt-1">{f.statement} <span className="text-xs text-slate-500">Sources: {f.source_record_ids.join(", ") || "none"}</span></p>) : <p className="text-slate-500">None recorded.</p>}</div>)}
                  {report.missing_information.length > 0 && <p>Missing information: {report.missing_information.join("; ")}</p>}
                  <p><strong>Recommendation:</strong> {report.recommended_resolution}</p>
                  <div className="flex flex-wrap gap-2"><Button size="sm" disabled={busy} onClick={() => void reviewInvestigation(investigation, "approve")}>Approve recommendation</Button><Button size="sm" variant="outline" disabled={busy} onClick={() => void reviewInvestigation(investigation, "reject")}>Reject</Button><Button size="sm" variant="outline" disabled={busy} onClick={() => void reviewInvestigation(investigation, "request_information")}>Request information</Button></div>
                </div>}
                {item.status === "open" && <Button className="mt-3" size="sm" variant="outline" disabled={busy} onClick={() => void resolveException(item)}>Resolve manually with reviewer note</Button>}
              </article>;
            })}
          </CardContent>
        </Card>
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>Invoice balances</CardTitle><p className="text-sm text-slate-600">Paid and outstanding amounts are derived from approved allocations.</p></CardHeader><CardContent className="max-h-72 space-y-2 overflow-auto">
          {balances.map((item) => <div key={item.invoice_id} className="flex flex-wrap justify-between gap-3 border-b pb-2 text-sm"><span>{item.invoice_number || item.invoice_id} · {item.vendor_name || "Vendor pending review"}</span><span>{item.currency} {item.paid_amount} paid · {item.outstanding_amount} outstanding</span></div>)}
          {!balances.length && <p className="text-sm text-slate-500">No invoices available.</p>}
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Vendor alias candidates</CardTitle><p className="text-sm text-slate-600">Unverified aliases are never used for scoring.</p></CardHeader><CardContent className="space-y-2">
          {aliases.length === 0 && <p className="text-sm text-slate-500">No alias candidates.</p>}
          {aliases.map((alias) => <div key={alias.id} className="flex items-center justify-between gap-3 border-b py-2 text-sm"><span>{alias.candidate_name} → {alias.normalized_name}</span>{alias.verified ? <span className="text-emerald-800">Verified</span> : <Button size="sm" variant="outline" onClick={() => void verifyAlias(alias)}>Verify alias</Button>}</div>)}
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Audit history</CardTitle><p className="text-sm text-slate-600">Recent reviewer and investigation actions.</p></CardHeader><CardContent className="max-h-72 space-y-2 overflow-auto">
          {audit.slice(0, 50).map((item) => <p key={item.id} className="border-b pb-2 text-xs text-slate-600">{new Date(item.created_at).toLocaleString()} · {item.action} · {item.entity_type} · {item.reason || "No note"}</p>)}
          {audit.length === 0 && <p className="text-sm text-slate-500">No audit events recorded yet.</p>}
        </CardContent></Card>
      </div>
    </main>
  );
}
