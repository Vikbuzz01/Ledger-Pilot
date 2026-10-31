import { DocumentsWorkspace } from "@/components/documents-workspace";

export default async function BusinessDocumentsPage({
  params,
}: {
  params: Promise<{ businessId: string }>;
}) {
  const { businessId } = await params;
  return <DocumentsWorkspace businessId={businessId} />;
}
