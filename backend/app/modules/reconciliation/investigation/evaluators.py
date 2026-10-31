"""Validate that a report stays within evidence returned by authorized tools."""

from app.modules.reconciliation.investigation.schemas import InvestigationReport


def evaluate_report(report: InvestigationReport, context: dict) -> InvestigationReport:
    allowed = set(context.get("available_record_ids", []))
    findings = (
        *report.verified_facts,
        *report.supporting_evidence,
        *report.hypotheses,
        *report.contradicting_evidence,
    )
    for finding in findings:
        if not set(finding.source_record_ids) <= allowed:
            raise ValueError("Investigation cited records outside its authorized evidence context")
    report.human_review_required = True
    return report
