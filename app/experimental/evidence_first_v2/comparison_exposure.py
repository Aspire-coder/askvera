"""Versioned, application-owned pre-exposure ledger artifact."""
from __future__ import annotations
LEDGER_VERSION="v2-05-preexposed-1"
def ledger_identity(records):
 rows=[]
 for r in records:
  if r.split.value=="development":rows.append((r.family,(r.source.source_family,r.source.version)if r.source else("unavailable",r.family),r.disposition.value))
 comparison=__import__(__package__+".comparison",fromlist=("_digest",))
 return comparison._digest((LEDGER_VERSION,tuple(sorted(rows))))
