# AskVera Documentation Scope

Create practical developer documentation for the AskVera repository.

Prioritize these topics:

1. End-to-end request flow from widget initialization through consent, retrieval, generation, validation, and response delivery.
2. Country and language isolation, including local policy records and globally available directory records.
3. Document ingestion: upload, preflight checks, extraction, section chunking, staging, validation, and publication.
4. Retrieval: OpenSearch section retrieval, locale filters, global-directory access, ranking, evidence gates, and fallback behavior.
5. Security: widget authentication, session resumption, PII handling, guardrails, redaction, admin RBAC, audit events, and production configuration validation.
6. Operations: deployment, health checks, rollback, analytics, support routing, and monitoring.
7. Widget/API integration and the important public endpoints.

Documentation rules:

- Treat `opensearch_section` as the current retrieval provider. Do not describe Bedrock Knowledge Bases as the live retrieval path.
- Distinguish current behavior from planned or gated hardened-profile behavior.
- Cite concrete file paths and important function or class names.
- Explain data ownership and where information is stored without reproducing secrets or customer data.
- Prefer short, readable Markdown pages with Mermaid diagrams where they clarify a flow.
- Do not invent infrastructure, permissions, or runtime behavior that is not supported by the source.
- Keep policy PDFs and customer-facing knowledge-base content out of this code wiki.
