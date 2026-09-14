# International Sponsoring Source Alignment

## Finding

The International Sponsoring Directory is already present in the AskVera
repository's existing chatbot document pipeline. It must not be added as a
second document or treated as a country-policy document.

The existing local extraction is:

`C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy\tmp\askvera-global-sponsoring\International_Sponsoring_Directory.directory.jsonl`

Its records use:

- `country`: `GLOBAL`
- `directory_section`: `sponsoring`
- `directory_kind`: `international_sponsoring`
- one record per `Welcome to Forever ...!` section

The local JSONL does not carry `access_scope`. Global access scope is applied
by the publication path. Live publication and index state were not checked by
this local source-alignment work.

The runtime already recognizes `directory_kind=international_sponsoring` and
keeps this content available to users in any market. A user's market controls
local company-policy documents; it does not prevent a question about another
country's international sponsoring directory entry.

## Source reconciliation

The supplied PDF is 235 pages. Its two wrapped country headings on pages 25
and 194 require bounded continuation-line handling. With that handling, local
extraction produces 115 country-section records, beginning on page 5 and
ending on page 235, which matches the workbook's `All Sections` sheet,
including its two Singapore entries. The existing frozen JSONL remains the
prior 113-record extraction and has the same source filename and record
structure.

The PDF is the factual source; the spreadsheet is the routing/index source;
the existing JSONL is the chatbot's current search representation. Do not
regenerate the frozen JSONL as part of this correction: a regenerated file
would shift ordinal section IDs and requires coordinated publication later.

## Required behavior

1. Reuse the existing global sponsoring document and extraction.
2. Do not copy the supplied PDF into a second chatbot document location.
3. Do not route international sponsoring questions through the user's local
   policy scope.
4. Resolve a named country to its own sponsoring section when one exists;
   otherwise use the serving section recorded by the directory.
5. Preserve the source page range and section metadata in every answer.
6. Do not infer missing countries, amounts, phone numbers, or policy facts from
   the workbook or general knowledge.

## Validation performed

- Supplied PDF: 235 pages.
- Corrected local extraction: `115` sponsoring records, reconciled against
  the workbook's `All Sections` entries, including duplicate Singapore.
- Existing frozen extraction: `113` sponsoring records; it was not regenerated.
- Local extraction records use `country=GLOBAL`; publication applies access
  scope. Live publication and index state were not checked.
- No duplicate sponsoring PDF is required for the chatbot.

This is a source-alignment correction only. It does not change the PDF,
country policy documents, the live index, or deployment state.
