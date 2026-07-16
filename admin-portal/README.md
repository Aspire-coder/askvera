# AskVera Operations

AskVera Operations is a responsive React and TypeScript admin portal with three connected views:

- **Live flow** replays recent requests across the same eight observable stages used by the chatbot backend.
- **Knowledge** uploads and indexes approved PDF, DOCX, text, Markdown, CSV, and HTML content.
- **Insights** shows users, questions, AI token usage, confidence, unanswered rate, feedback, topics, countries, languages, trends, and answer-level diagnostics.

## Run locally

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

The portal opens at `http://127.0.0.1:5176`. Without an API key it deliberately uses presentation-ready demo data. Choose **Demo mode** in the sidebar to enter the separately managed `ADMIN_API_KEY`; the value is held only in the current tab's `sessionStorage`.

## Build

```powershell
npm ci
npm run typecheck
npm run build
```

Set `VITE_API_URL` to the HTTPS API origin before building for a separate static host. Never put the admin key in a Vite environment variable or in the generated bundle.

## Supported knowledge documents

The uploader accepts PDF, DOCX, TXT, Markdown, CSV, HTML, and HTM files up to the configured limit. Each upload carries country, language, document type, access scope, version, and optional effective-date metadata. The generic extractor uses headings and overlapping retrieval-sized chunks, so it is not tied to policy formatting and also supports product information, training, FAQs, marketing, legal, and operational material.

Image-only scanned PDFs require an OCR stage before ingestion. The current service detects that no readable text was extracted and marks the job failed rather than indexing an empty or misleading document.
