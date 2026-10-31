"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest, clearSession, getToken } from "@/lib/api";

type DocumentRow = {
  id: string;
  business_id: string;
  document_type: "bank_csv" | "invoice_pdf";
  original_filename: string;
  sha256: string;
  size_bytes: number;
  status: "processing" | "review_required" | "processed" | "failed";
  validation_errors: { code: string; message: string }[];
  created_at: string;
};
type Invoice = {
  id: string;
  invoice_number: string | null;
  vendor_name: string | null;
  invoice_date: string | null;
  due_date: string | null;
  total_amount: string | null;
  currency: string | null;
  validation_errors: { field?: string; code: string; message: string }[];
};
type Transaction = {
  id: string;
  source_row_number: number;
  transaction_date: string | null;
  description: string | null;
  amount: string | null;
  currency: string | null;
  external_reference: string | null;
  validation_errors: { field?: string; code: string; message: string }[];
};
type Provenance = {
  entity_type: string;
  entity_id: string;
  field_name: string;
  extracted_value: string | null;
  source_location: string;
  value_origin: "extracted" | "user_verified" | "system_derived";
};
type Detail = { document: DocumentRow; invoices: Invoice[]; transactions: Transaction[]; provenance: Provenance[] };

function StatusPill({ status }: { status: DocumentRow["status"] }) {
  const style = {
    processing: "bg-blue-50 text-blue-800",
    review_required: "bg-amber-50 text-amber-900",
    processed: "bg-emerald-50 text-emerald-800",
    failed: "bg-rose-50 text-rose-800",
  }[status];
  const label = {
    processing: "Processing",
    review_required: "Review required",
    processed: "Verified",
    failed: "Processing failed",
  }[status];
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${style}`}>{label}</span>;
}

function ValidationErrors({ errors }: { errors: { message: string }[] }) {
  if (!errors.length) return null;
  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
      <p className="font-semibold">Review needed</p>
      <ul className="mt-1 list-inside list-disc space-y-1">
        {errors.map((error, index) => <li key={`${error.message}-${index}`}>{error.message}</li>)}
      </ul>
    </div>
  );
}

function ProvenanceNote({ item }: { item?: Provenance }) {
  if (!item) return <span className="text-xs text-amber-800">No extraction source recorded</span>;
  return (
    <span className="text-xs text-slate-500">
      {item.value_origin === "user_verified" ? "User verified" : item.value_origin === "system_derived" ? "System derived" : "Extracted"}
      {" · "}{item.source_location}
    </span>
  );
}

function InvoiceEditor({
  invoice,
  detail,
  businessId,
  onSaved,
  onError,
}: {
  invoice: Invoice;
  detail: Detail;
  businessId: string;
  onSaved: (detail: Detail) => void;
  onError: (message: string) => void;
}) {
  const [values, setValues] = useState({
    invoice_number: invoice.invoice_number ?? "",
    vendor_name: invoice.vendor_name ?? "",
    invoice_date: invoice.invoice_date ?? "",
    due_date: invoice.due_date ?? "",
    total_amount: invoice.total_amount ?? "",
    currency: invoice.currency ?? "",
  });
  const [saving, setSaving] = useState(false);
  const sources = useMemo(
    () => new Map(detail.provenance.filter((p) => p.entity_id === invoice.id).map((p) => [p.field_name, p])),
    [detail.provenance, invoice.id],
  );

  useEffect(() => {
    setValues({
      invoice_number: invoice.invoice_number ?? "",
      vendor_name: invoice.vendor_name ?? "",
      invoice_date: invoice.invoice_date ?? "",
      due_date: invoice.due_date ?? "",
      total_amount: invoice.total_amount ?? "",
      currency: invoice.currency ?? "",
    });
  }, [invoice]);

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    onError("");
    try {
      const result = await apiRequest<Detail>(
        `/api/v1/businesses/${businessId}/documents/${detail.document.id}/invoices/${invoice.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ ...values, due_date: values.due_date || null }),
        },
      );
      onSaved(result);
    } catch (cause) {
      onError(cause instanceof Error ? cause.message : "Invoice values could not be verified.");
    } finally {
      setSaving(false);
    }
  }

  function field(name: keyof typeof values, label: string, type = "text", required = false) {
    return (
      <label className="block space-y-1 text-sm font-medium">
        {label}
        <Input
          type={type}
          step={type === "number" ? "any" : undefined}
          required={required}
          value={values[name]}
          onChange={(event) => setValues((current) => ({ ...current, [name]: event.target.value }))}
        />
        <ProvenanceNote item={sources.get(name)} />
      </label>
    );
  }

  return (
    <form className="space-y-4" onSubmit={verify}>
      <ValidationErrors errors={invoice.validation_errors} />
      <div className="grid gap-3 sm:grid-cols-2">
        {field("invoice_number", "Invoice number", "text", true)}
        {field("vendor_name", "Vendor", "text", true)}
        {field("invoice_date", "Invoice date", "date", true)}
        {field("due_date", "Due date", "date")}
        {field("total_amount", "Total amount", "number", true)}
        {field("currency", "Currency code", "text", true)}
      </div>
      <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Verify invoice fields"}</Button>
    </form>
  );
}

function TransactionEditor({
  transaction,
  detail,
  businessId,
  onSaved,
  onError,
}: {
  transaction: Transaction;
  detail: Detail;
  businessId: string;
  onSaved: (detail: Detail) => void;
  onError: (message: string) => void;
}) {
  const [values, setValues] = useState({
    transaction_date: transaction.transaction_date ?? "",
    description: transaction.description ?? "",
    amount: transaction.amount ?? "",
    currency: transaction.currency ?? "",
    external_reference: transaction.external_reference ?? "",
  });
  const [saving, setSaving] = useState(false);
  const sources = useMemo(
    () => new Map(detail.provenance.filter((p) => p.entity_id === transaction.id).map((p) => [p.field_name, p])),
    [detail.provenance, transaction.id],
  );

  useEffect(() => {
    setValues({
      transaction_date: transaction.transaction_date ?? "",
      description: transaction.description ?? "",
      amount: transaction.amount ?? "",
      currency: transaction.currency ?? "",
      external_reference: transaction.external_reference ?? "",
    });
  }, [transaction]);

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    onError("");
    try {
      const result = await apiRequest<Detail>(
        `/api/v1/businesses/${businessId}/documents/${detail.document.id}/transactions/${transaction.id}`,
        { method: "PATCH", body: JSON.stringify(values) },
      );
      onSaved(result);
    } catch (cause) {
      onError(cause instanceof Error ? cause.message : "Transaction values could not be verified.");
    } finally {
      setSaving(false);
    }
  }

  function field(name: keyof typeof values, label: string, type = "text", required = false) {
    return (
      <label className="block space-y-1 text-sm font-medium">
        {label}
        <Input
          type={type}
          step={type === "number" ? "any" : undefined}
          required={required}
          value={values[name]}
          onChange={(event) => setValues((current) => ({ ...current, [name]: event.target.value }))}
        />
        <ProvenanceNote item={sources.get(name)} />
      </label>
    );
  }

  return (
    <form className="space-y-4" onSubmit={verify}>
      <ValidationErrors errors={transaction.validation_errors} />
      <div className="grid gap-3 sm:grid-cols-2">
        {field("transaction_date", "Transaction date", "date", true)}
        {field("description", "Description", "text", true)}
        {field("amount", "Amount", "number", true)}
        {field("currency", "Currency code", "text", true)}
        {field("external_reference", "Reference")}
      </div>
      <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Verify transaction fields"}</Button>
    </form>
  );
}

export function DocumentsWorkspace({ businessId }: { businessId: string }) {
  const router = useRouter();
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [documentType, setDocumentType] = useState<DocumentRow["document_type"]>("bank_csv");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadDocuments = useCallback(async () => {
    try {
      const rows = await apiRequest<DocumentRow[]>(`/api/v1/businesses/${businessId}/documents`);
      setDocuments(rows);
    } catch (cause) {
      if (cause instanceof Error && "status" in cause && cause.status === 401) {
        clearSession();
        router.push("/login");
      } else {
        setError(cause instanceof Error ? cause.message : "Documents could not be loaded.");
      }
    } finally {
      setLoading(false);
    }
  }, [businessId, router]);

  useEffect(() => { void loadDocuments(); }, [loadDocuments]);

  async function openDocument(document: DocumentRow) {
    setError("");
    setDetail(null);
    try {
      const result = await apiRequest<Detail>(`/api/v1/businesses/${businessId}/documents/${document.id}`);
      setDetail(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Document details could not be loaded.");
    }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    const form = event.currentTarget;
    setUploading(true);
    setError("");
    setNotice("");
    const body = new FormData();
    body.set("document_type", documentType);
    body.set("file", file);
    try {
      const result = await apiRequest<{ document: DocumentRow; duplicate: boolean }>(
        `/api/v1/businesses/${businessId}/documents`,
        { method: "POST", body },
      );
      setNotice(result.duplicate ? "This exact file was already uploaded to this business. Existing extraction was kept." : "File uploaded and extracted. Review the extracted values before accepting them.");
      setFile(null);
      form.reset();
      await loadDocuments();
      await openDocument(result.document);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Upload failed. Check the file and try again.");
    } finally {
      setUploading(false);
    }
  }

  async function retry(document: DocumentRow) {
    setError("");
    try {
      const updated = await apiRequest<DocumentRow>(
        `/api/v1/businesses/${businessId}/documents/${document.id}/process`,
        { method: "POST" },
      );
      await loadDocuments();
      await openDocument(updated);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Processing could not be retried.");
    }
  }

  async function openSource(documentId: string) {
    setError("");
    const popup = window.open("about:blank", "_blank");
    if (!popup) {
      setError("Allow pop-ups to open the protected source document.");
      return;
    }
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/businesses/${businessId}/documents/${documentId}/file`,
        { headers: { Authorization: `Bearer ${getToken()}` }, cache: "no-store" },
      );
      if (!response.ok) throw new Error("Source document could not be opened.");
      const objectUrl = URL.createObjectURL(await response.blob());
      popup.location.href = objectUrl;
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    } catch (cause) {
      popup.close();
      setError(cause instanceof Error ? cause.message : "Source document could not be opened.");
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-6xl px-5 py-10 sm:px-8">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-6">
        <div>
          <Link href="/dashboard" className="text-sm font-medium text-gold-400 underline">← Business selection</Link>
          <p className="mt-4 text-xs font-semibold uppercase tracking-[0.2em] text-gold-400">LedgerPilot</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">Documents</h1>
          <p className="mt-2 text-sm text-slate-600">Statements and invoices remain private to this business.</p>
        </div>
        <span className="max-w-xs break-all text-xs text-slate-500">Business {businessId}</span>
      </header>

      {error && <p role="alert" className="mt-5 rounded-md bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
      {notice && <p role="status" className="mt-5 rounded-md bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</p>}

      <section className="mt-7 grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Upload financial document</CardTitle>
              <p className="text-sm text-slate-600">CSV bank statements or text-based PDF invoices. Maximum size is configured by the server.</p>
            </CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={upload}>
                <label className="block space-y-1.5 text-sm font-medium">
                  Document type
                  <select
                    className="h-10 w-full rounded-lg border border-slate-300 bg-elevated px-3 text-slate-900 focus:border-gold-400 focus:outline-none focus:ring-2 focus:ring-gold-400/30"
                    value={documentType}
                    onChange={(event) => { setDocumentType(event.target.value as DocumentRow["document_type"]); setFile(null); }}
                  >
                    <option value="bank_csv">Bank statement (CSV)</option>
                    <option value="invoice_pdf">Invoice (PDF)</option>
                  </select>
                </label>
                <label className="block space-y-1.5 text-sm font-medium">
                  Choose file
                  <Input
                    key={documentType}
                    type="file"
                    required
                    accept={documentType === "bank_csv" ? ".csv,text/csv" : ".pdf,application/pdf"}
                    onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  />
                </label>
                <Button type="submit" disabled={uploading || !file}>{uploading ? "Uploading and extracting…" : "Upload document"}</Button>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Uploaded documents</CardTitle>
              <p className="text-sm text-slate-600">Select a document to review its extracted fields and source locations.</p>
            </CardHeader>
            <CardContent>
              {loading ? <p className="text-sm text-slate-600">Loading documents…</p> : documents.length === 0 ? (
                <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-600">No documents uploaded to this business yet.</p>
              ) : (
                <ul className="space-y-2">
                  {documents.map((document) => (
                    <li key={document.id}>
                      <button
                        type="button"
                        onClick={() => void openDocument(document)}
                        className="flex w-full items-center justify-between gap-3 rounded-lg border border-slate-200 p-3 text-left hover:bg-slate-50"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium">{document.original_filename}</span>
                          <span className="mt-1 block text-xs text-slate-500">
                            {document.document_type === "bank_csv" ? "Bank CSV" : "Invoice PDF"} · {Math.ceil(document.size_bytes / 1024)} KB
                          </span>
                        </span>
                        <StatusPill status={document.status} />
                      </button>
                      {document.status === "failed" && (
                        <Button variant="ghost" size="sm" className="mt-1" onClick={() => void retry(document)}>Retry processing</Button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>

        <div>
          {!detail ? (
            <Card>
              <CardHeader>
                <CardTitle>Extraction review</CardTitle>
                <p className="text-sm leading-6 text-slate-600">Extracted information is unverified until a user reviews and confirms its fields. Incomplete or ambiguous values stay marked for review.</p>
              </CardHeader>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <CardTitle>{detail.document.original_filename}</CardTitle>
                  <StatusPill status={detail.document.status} />
                </div>
                <p className="text-xs text-slate-500">SHA-256 {detail.document.sha256}</p>
                {detail.document.status === "review_required" && (
                  <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-950">
                    Human review required. Extracted values are suggestions from the source and have not been confirmed.
                  </p>
                )}
                <ValidationErrors errors={detail.document.validation_errors} />
                <Button type="button" variant="outline" size="sm" onClick={() => void openSource(detail.document.id)}>
                  Open source document
                </Button>
              </CardHeader>
              <CardContent className="space-y-6">
                {detail.invoices.map((invoice) => (
                  <section key={invoice.id} className="space-y-4 border-t border-slate-200 pt-5">
                    <h3 className="font-semibold">Extracted invoice · verify each field</h3>
                    <InvoiceEditor
                      key={invoice.id}
                      invoice={invoice}
                      detail={detail}
                      businessId={businessId}
                      onSaved={setDetail}
                      onError={setError}
                    />
                  </section>
                ))}
                {detail.transactions.map((transaction) => (
                  <section key={transaction.id} className="space-y-4 border-t border-slate-200 pt-5">
                    <h3 className="font-semibold">Bank transaction · source CSV row {transaction.source_row_number}</h3>
                    <TransactionEditor
                      key={transaction.id}
                      transaction={transaction}
                      detail={detail}
                      businessId={businessId}
                      onSaved={setDetail}
                      onError={setError}
                    />
                  </section>
                ))}
                {!detail.invoices.length && !detail.transactions.length && (
                  <p className="text-sm text-slate-600">No structured records were extracted. Correct the source file and upload it again.</p>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </section>
    </main>
  );
}
