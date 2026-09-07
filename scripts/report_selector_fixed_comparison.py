"""Render recorded selector outputs, not chatbot answer-quality scores."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re


def report(folder):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    rows = [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(folder.glob("*-*-*.json")) if path.name != "manifest.json"]
    sides = [side for side in ("current", "candidate", "ranking", "binding", "combined", "scoped", "verdict", "structural")
             if any(row["side"] == side for row in rows)]
    lines = ["# Isolated selector comparison", "",
             "Selector decisions and experimental drafts only, not final chatbot answers or a release gate.", "",
             f'Candidate variant: {manifest.get("candidate_variant", "see manifest requests")}. Captures: {len(rows)}.', "",
             "| Version | Decision/evidence checks passed | Attempts | Execution errors |",
             "| --- | ---: | ---: | ---: |"]
    for side in sides:
        values = [row for row in rows if row["side"] == side]
        lines.append(f'| {side} | {sum(row.get("passed") is True for row in values)} | '
                     f'{len(values)} | {sum("error_type" in row for row in values)} |')
    usage = Counter()
    for row in rows:
        usage.update({key: value for key, value in (row.get("usage") or {}).items()
                      if isinstance(value, int)})
    lines += ["", f'Recorded token usage: {dict(usage)}.', "",
              "Results are exploratory on reused cases. A passed check does not certify all generated claims.", ""]
    for case in manifest["cases"]:
        lines += [f'## {case["id"]}', "", case["question"], "",
                  f'Expected support: {case["expected"]}. Governing sections: {case["governing_sections"]}.', ""]
        for repeat in range(1, manifest["repeats"] + 1):
            for side in sides:
                row = next((row for row in rows if row["id"] == case["id"]
                            and row["repeat"] == repeat and row["side"] == side), None)
                lines += [f"### Repeat {repeat}: {side}", ""]
                if row is None:
                    lines += ["Missing capture.", ""]
                    continue
                lines += [str(row.get("assessment", row.get("error_type"))), ""]
                raw = row.get("output", "No output captured.")
                fence = "`" * max(3, 1 + max((len(match) for match in re.findall(r"`+", raw)), default=0))
                lines += [fence + "text", raw, fence, ""]
    with (folder / "COMPARISON.md").open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    print(f"Rendered {len(rows)} captured decisions in {folder.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", type=Path, nargs="+")
    args = parser.parse_args()
    for folder in args.folders:
        report(folder)


if __name__ == "__main__":
    main()
