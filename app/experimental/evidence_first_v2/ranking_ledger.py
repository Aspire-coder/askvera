"""Separately authored immutable V2-06 pre-exposure assignment table."""
from __future__ import annotations
import hashlib

LEDGER_VERSION="v2-06-preexposed-3"
# Reviewed static lineage-to-axis assignments. This table intentionally imports no authority.
_ASSIGNMENTS=(
 ("fd062ba43aa11031f4d705c57e93ac9892d68ded4906bab80e02488178ea1026","synthetic","development"),
 ("a464a1f683ca8da4ae55836dec06d2bd06956f7c3a3fe7feb064662be9870d49","synthetic","development"),
 ("e57d964d48970fe1885b3fbaec14685d3617f10ea32eb6050b933d7f0ec4384b","synthetic","development"),
 ("c2dea02c48a05263bd61d0813eca6f683285418a177b54b0651b0c56d52491f2","real","development"),
 ("af585f70cbbca0a6cecde984226c9ae8add58e74831559b91a440c206e69dcf9","synthetic","held_out"),
)
LEDGER_CONTENT_ID=hashlib.sha256(repr((LEDGER_VERSION,_ASSIGNMENTS)).encode("utf-8")).hexdigest()
def assignments():return _ASSIGNMENTS
def validate_assignments(captures,expected_version):
 if expected_version!=LEDGER_VERSION:raise ValueError("ledger version")
 for capture in captures:
  if (capture.lineage,capture.provenance,capture.split) not in _ASSIGNMENTS:raise ValueError("pre-exposure assignment")
