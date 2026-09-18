from __future__ import annotations
from dataclasses import replace
import unittest
from app.experimental.evidence_first_v2 import ranking as r
from app.experimental.evidence_first_v2 import ranking_fixture as f
from app.experimental.evidence_first_v2.ranking_ledger import LEDGER_VERSION,LEDGER_CONTENT_ID,assignments
P=r.StrategyParameters(); IDS=r._PINNED_CANONICAL_IDS; V=r._PINNED_AUTHORITY_VERSION; A=r._PINNED_AUTHORITY_CONTENT_ID; L=r._PINNED_LEDGER_CONTENT_ID
def report(order=("current-wins","miss","empty","real-unavailable","reviewed-rejected"),p=P):return r.run_owned(order,"run",p,V,A,LEDGER_VERSION,L)
class T(unittest.TestCase):
 def test_all_32_exact_tuple_boundaries_reject_tuple_subclasses(self):
  class TupleSubclass(tuple):pass
  S=TupleSubclass;good=report(("current-wins",));row=good.rows[0];axis=good.axes[0]
  cases=[]
  for capture in (f.CURRENT_WINS,f.EMPTY,f.UNAVAILABLE,f.REJECTED):
   for field in ("channels","current_order","hits","witnesses"):
    cases.append(lambda c=capture,n=field:replace(c,**{n:S(getattr(c,n))}))
  cases += [
   lambda:replace(f.Z,span=S(f.Z.span)),lambda:replace(f.Z,scores=S(f.Z.scores)),lambda:replace(f.Z,scores=(S(f.Z.scores[0]),)+f.Z.scores[1:]),lambda:replace(f.W,span=S(f.W.span)),
   lambda:r.StrategyParameters(weights=S(P.weights)),lambda:r.StrategyParameters(weights=(S(P.weights[0]),)+P.weights[1:]),lambda:r.CaseRow(row.case_id,row.state,row.reason,S(row.metrics)),
   lambda:r.Axis(axis.provenance,axis.split,S(axis.cases),axis.total,axis.comparable,axis.unavailable,axis.rejected,axis.denominators),lambda:r.Axis(axis.provenance,axis.split,axis.cases,axis.total,axis.comparable,axis.unavailable,axis.rejected,S(axis.denominators)),lambda:r.Axis(axis.provenance,axis.split,axis.cases,axis.total,axis.comparable,axis.unavailable,axis.rejected,(S(axis.denominators[0]),)+axis.denominators[1:]),
   lambda:f.Authority(f.authority().version,S(f.authority().records)),
   lambda:replace(good,canonical_ids=S(good.canonical_ids)),lambda:replace(good,ordered_case_ids=S(good.ordered_case_ids)),lambda:replace(good,capture_identities=S(good.capture_identities)),lambda:replace(good,rows=S(good.rows)),lambda:replace(good,axes=S(good.axes)),
  ]
  self.assertEqual(len(cases),32)
  for factory in cases:
   with self.assertRaises(ValueError):factory()
  self.assertEqual(report(("current-wins",)).ordered_case_ids,("current-wins",))
 def test_only_owned_routes(self):
  self.assertTrue(callable(r.run_owned) and callable(r.validate_owned))
  for n in ("evaluate","validate_report","evaluate_owned","validate_owned_report"):self.assertFalse(hasattr(r,n))
 def test_authority_pinned_against_public_supplier_and_alias_reassignment(self):
  original=f.authority; original_target=f._AUTHORITY
  try:
   f.authority=lambda:replace(original(),records=(replace(f.CURRENT_WINS,current_order=("a","z")),)+original().records[1:])
   f._AUTHORITY=replace(original_target,records=(replace(f.CURRENT_WINS,current_order=("a","z")),)+original_target.records[1:])
   x=report(("current-wins",));self.assertEqual(x.rows[0].metrics[0].rank,1)
   self.assertEqual(r.validate_owned(IDS,("current-wins",),"run",P,V,A,LEDGER_VERSION,L,x),x)
  finally:f.authority=original;f._AUTHORITY=original_target
 def test_static_ledger_survives_fixture_reassignment_and_reload(self):
  self.assertIsInstance(assignments(),tuple);self.assertTrue(LEDGER_CONTENT_ID)
  self.assertEqual(report(("current-wins",)).ledger_version,LEDGER_VERSION)
  self.assertEqual(replace(f.CURRENT_WINS,family="other").lineage,f.CURRENT_WINS.lineage)
  self.assertNotEqual(replace(f.CURRENT_WINS,split="held_out").identity,f.CURRENT_WINS.identity)
 def test_public_authority_and_ledger_aliases_cannot_relabel_acceptance(self):
  import app.experimental.evidence_first_v2.ranking_ledger as ledger
  old_authority=r.AUTHORITY_CONTENT_ID;old_version=ledger.LEDGER_VERSION;old_table=ledger._ASSIGNMENTS
  try:
   r.AUTHORITY_CONTENT_ID="attacker";ledger.LEDGER_VERSION="attacker";ledger._ASSIGNMENTS=()
   self.assertEqual(report(("current-wins",)).authority_content_id,A)
   with self.assertRaises(ValueError):r.run_owned(("current-wins",),"run",P,V,"attacker",LEDGER_VERSION,L)
   with self.assertRaises(ValueError):r.run_owned(("current-wins",),"run",P,V,A,"attacker",L)
  finally:r.AUTHORITY_CONTENT_ID=old_authority;ledger.LEDGER_VERSION=old_version;ledger._ASSIGNMENTS=old_table
 def test_lineage_deduplicates_hits_and_includes_witnesses(self):
  duplicate=replace(f.CURRENT_WINS,hits=(f.Z,f.A,replace(f.Z,candidate_id="other",scores=(("text",3,10.0),("vector",3,1.0)))),current_order=("z","a","other"))
  self.assertEqual(duplicate.lineage,f.CURRENT_WINS.lineage)
  self.assertNotEqual(replace(f.CURRENT_WINS,witnesses=(replace(f.W,content_digest="other"),)).lineage,f.CURRENT_WINS.lineage)
 def test_strict_nested_constructor_shapes(self):
  with self.assertRaises(ValueError):r.StrategyParameters(rrf_k=1)
  with self.assertRaises(ValueError):r.StrategyParameters(weights=[("text",1.0),("vector",1.0)])
  with self.assertRaises(ValueError):r.StrategyParameters(weights=(("text",1),("vector",1.0)))
  with self.assertRaises(ValueError):r.Metric(r.Strategy.CURRENT,True,False,1,1.0)
  with self.assertRaises(ValueError):r.CaseRow("x",r.State.COMPLETED,None,[])
  with self.assertRaises(ValueError):r.Axis("synthetic","development",(),0,0,0,0,[])
  with self.assertRaises(ValueError):f.Authority("",())
  with self.assertRaises(ValueError):replace(f.CURRENT_WINS,current_order=list(f.CURRENT_WINS.current_order))
  with self.assertRaises(ValueError):replace(f.UNAVAILABLE,channels=[])
 def test_axis_and_report_local_uniqueness(self):
  good=report(("current-wins",));row=good.rows[0]
  with self.assertRaises(ValueError):r.Axis("synthetic","development",(row,row),2,2,0,0,tuple((s,2) for s in r.Strategy))
  with self.assertRaises(ValueError):replace(good,canonical_ids=("outside",))
  with self.assertRaises(ValueError):replace(good,capture_identities=("",))
 def test_fixed_rrf_finite_weights_and_channel_union(self):
  high=replace(f.Z,scores=(("text",1,1e308),("vector",2,-1e308)));low=replace(f.A,scores=(("text",2,-1e308),("vector",1,1e308)));c=replace(f.CURRENT_WINS,hits=(high,low))
  self.assertEqual(r._ordered(c,r.Strategy.NORMALIZED,r.StrategyParameters(weights=(("text",1e308),("vector",1e308)))),("a","z"))
  with self.assertRaises(ValueError):replace(f.CURRENT_WINS,hits=(replace(f.Z,scores=()),f.A))
  with self.assertRaises(ValueError):replace(f.CURRENT_WINS,channels=(r.ChannelConfig("text",10,"failed","unicode-word-v1"),r.ChannelConfig("vector",10,"failed","embedding-offline-v1")),hits=(),current_order=())
  with self.assertRaises(ValueError):replace(f.EMPTY,channels=(r.ChannelConfig("text",10,"failed","unicode-word-v1"),r.ChannelConfig("vector",10,"empty","embedding-offline-v1")))
  partial=replace(f.CURRENT_WINS,channels=(r.ChannelConfig("text",10,"complete","unicode-word-v1"),r.ChannelConfig("vector",10,"failed","embedding-offline-v1")),hits=(replace(f.Z,scores=(("text",1,10.0),)),replace(f.A,scores=(("text",2,1.0),))))
  self.assertEqual(r._ordered(partial,r.Strategy.NORMALIZED,P),("z","a"))
 def test_scope_source_access_and_analyzer_are_pinned(self):
  with self.assertRaises(ValueError):r.Scope("ZZ",None,"FBO","en")
  with self.assertRaises(ValueError):replace(f.CURRENT_WINS,hits=(replace(f.Z,source_market="KE"),f.A))
  with self.assertRaises(ValueError):replace(f.CURRENT_WINS,hits=(replace(f.Z,access_scope="approved_internal"),f.A))
  original=r.APPROVED_ANALYZERS
  try:
   r.APPROVED_ANALYZERS=(("text","bad"),("vector","bad"))
   with self.assertRaises(ValueError):r.ChannelConfig("text",10,"complete","bad")
  finally:r.APPROVED_ANALYZERS=original
  original_markets=r.APPROVED_MARKETS;original_id=r.ANALYZER_CONTENT_ID
  try:
   r.APPROVED_MARKETS=("ZZ",);r.ANALYZER_CONTENT_ID="attacker"
   with self.assertRaises(ValueError):r.Scope("ZZ",None,"FBO","en")
   self.assertEqual(r.ChannelConfig("text",10,"complete","unicode-word-v1").analyzer_content_id,"v2-06-analyzers-1")
  finally:r.APPROVED_MARKETS=original_markets;r.ANALYZER_CONTENT_ID=original_id
 def test_validate_independent_expected_identity(self):
  x=report(("current-wins",));self.assertEqual(r.validate_owned(IDS,("current-wins",),"run",P,V,A,LEDGER_VERSION,L,x),x)
  for args in ((IDS,("current-wins",),"run",P,V,"wrong",LEDGER_VERSION,L),(IDS,("current-wins",),"run",P,"wrong",A,LEDGER_VERSION,L),(IDS,("current-wins",),"run",P,V,A,"wrong",L),(IDS,("current-wins",),"run",P,V,A,LEDGER_VERSION,"wrong")):
   with self.assertRaises(ValueError):r.validate_owned(*args,x)
