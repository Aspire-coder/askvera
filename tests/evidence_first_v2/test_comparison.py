from __future__ import annotations
from dataclasses import replace
import hashlib
import unittest
from app.experimental.evidence_first_v2 import comparison as c
from app.experimental.evidence_first_v2.comparison_fixture import RECORDS, UNAVAILABLE, POSITIVE_CANDIDATES, NEGATIVE_CANDIDATES, fixture_evaluator
def replay(r,side,answer=None):
 answer=answer or ("old-"+r.case_id if side=="baseline" else "new-"+r.case_id)
 return c.Replay(r.baseline_artifact if side=="baseline" else r.candidate_artifact,r.baseline_content if side=="baseline" else hashlib.sha256(answer.encode()).hexdigest(),c._input(r),r.baseline_code if side=="baseline" else r.candidate_code,"saved_baseline" if side=="baseline" else "deterministic_v2",answer)
def ev(r,x,side,values=None):return c.Observation(r.case_id,r.record_id,x.content_id,side,"eval-v1",tuple((m,True if values is None else values[m])for m in c.METRICS))
def manifest(ids=("manager",)):return c.admit_owned(ids,"impl-v1","eval-v1","comparison-v1")
def rebuilt(result,**changes):
 data={n:getattr(result,n)for n in ("run_id","case_id","outcome","reason","baseline","candidate","baseline_observation","candidate_observation","transitions")};data.update(changes)
 data["transitions"]=tuple(sorted(data["transitions"]))
 return c.CaseResult(**data,identity=c._digest(tuple(data[n]for n in ("run_id","case_id","outcome","reason","baseline","candidate","baseline_observation","candidate_observation","transitions"))))
def rebuilt_report(m,result):
 summary=c._summaries(m.records,(result,));return c.Report(m.identity,result.run_id,(result,),summary,c._digest((m.identity,result.run_id,(result.identity,),tuple(sorted(summary,key=lambda x:(x.provenance.value,x.split.value))))))
class ComparisonTests(unittest.TestCase):
 def test_fixture_eight_hand_authored_families(self):
  self.assertEqual(tuple(x.case_id for x in RECORDS),("manager","p001_identity","public_contact","role_figure","policy_sponsoring","multilingual_followup","refusal","harmful_claim"));self.assertTrue(all(x.obligations and len(x.expected_constraints)>=2 for x in RECORDS))
 def test_fixture_content_controls(self):
  text={x.case_id:x.source.data.decode()for x in RECORDS}
  for key,word in (("manager","training"),("p001_identity","Example Forever"),("public_contact","+254"),("role_figure","monthly"),("policy_sponsoring","Kenya"),("multilingual_followup","Belgium"),("refusal","$500"),("harmful_claim","diabetes")):self.assertIn(word,text[key])
 def test_owned_admission_rejects_unknown_duplicate_and_blank(self):
  for ids in ((),("unknown",),("manager","manager"),(" ",)):
   with self.assertRaises(ValueError):manifest(ids)
 def test_valid_owned_path_and_api(self):
  m=manifest();r=c.run_owned(m,lambda x:replay(x,"baseline"),lambda x:replay(x,"candidate"),ev);self.assertEqual(r.results[0].outcome,c.Outcome.AVAILABLE);self.assertEqual(c.validate_report(m,r),r);self.assertEqual(len(c.summarize(m,r)),4)
 def test_unavailable_zero_callbacks(self):
  calls=[];r=c.run_owned(manifest(("real-source-unavailable","held-out-unavailable")),lambda x:calls.append(1),lambda x:calls.append(2),lambda *x:calls.append(3));self.assertEqual(calls,[]);self.assertTrue(all(x.reason=="unavailable_evidence"for x in r.results))
 def test_manifest_tamper_before_callbacks(self):
  m=manifest();bad=replace(m,authority_identity="0"*64,identity=c._digest(("0"*64,m.ledger_identity,m.implementation_id,m.evaluator_version,m.comparison_id,tuple(x.identity for x in m.records))));calls=[]
  with self.assertRaises(ValueError):c.run_owned(bad,lambda x:calls.append(1),lambda x:calls.append(2),lambda *x:calls.append(3))
  self.assertEqual(calls,[])
 def test_stale_ledger_reset_before_callbacks(self):
  m=manifest();bad=replace(m,ledger_identity="0"*64,identity=c._digest((m.authority_identity,"0"*64,m.implementation_id,m.evaluator_version,m.comparison_id,tuple(x.identity for x in m.records))))
  with self.assertRaises(ValueError):c.run_owned(bad,lambda x:None,lambda x:None,lambda *x:None)
 def test_cross_call_ledger_is_owned_preexposed(self):self.assertEqual(manifest().ledger_identity,manifest().ledger_identity)
 def test_replay_wrong_side_and_input_fail(self):
  m=manifest();self.assertEqual(c.run_owned(m,lambda x:replay(x,"candidate"),lambda x:replay(x,"candidate"),ev).results[0].reason,"baseline_unavailable")
  self.assertEqual(c.run_owned(m,lambda x:replay(x,"baseline"),lambda x:replace(replay(x,"candidate"),input_id="bad"),ev).results[0].reason,"candidate_unavailable")
 def test_observation_all_bindings_fail(self):
  m=manifest()
  for bad in (lambda r,x,s:replace(ev(r,x,s),case_id="p001_identity"),lambda r,x,s:replace(ev(r,x,s),expected_record_id="bad"),lambda r,x,s:replace(ev(r,x,s),replay_digest="0"*64),lambda r,x,s:replace(ev(r,x,s),evaluator_version="old")):
   self.assertEqual(c.run_owned(m,lambda x:replay(x,"baseline"),lambda x:replay(x,"candidate"),bad).results[0].reason,"evaluator_fault")
 def test_fault_baseline_skips_candidate(self):
  calls=[];r=c.run_owned(manifest(),lambda x:None,lambda x:calls.append(1),lambda *x:calls.append(2));self.assertEqual(r.results[0].reason,"baseline_unavailable");self.assertEqual(calls,[])
 def test_evaluator_exception_sanitized(self):self.assertEqual(c.run_owned(manifest(),lambda x:replay(x,"baseline"),lambda x:replay(x,"candidate"),lambda *x:(_ for _ in ()).throw(RuntimeError("secret"))).results[0].reason,"evaluator_fault")
 def test_obligation_and_request_schema_gaps(self):
  with self.assertRaises(ValueError):c.Obligation("a",())
  with self.assertRaises(ValueError):c.RequestContext("id","a","b","t","US",True,"FBO","en","v1")
  with self.assertRaises(ValueError):c.RequestContext("id","a","b","t","us","US","FBO","en","v1")
 def test_enum_encoding_is_not_plain_string(self):self.assertNotEqual(c._canon(c.Provenance.SYNTHETIC),c._canon("synthetic"))
 def test_source_boolean_span_and_quote_reject(self):
  s=RECORDS[0].source
  with self.assertRaises(ValueError):c.SourceBinding(s.source_id,s.version,s.source_family,s.data,True,s.end,s.quote)
  with self.assertRaises(ValueError):c.SourceBinding(s.source_id,s.version,s.source_family,s.data,s.start,s.end,b"wrong")
 def test_result_and_report_payload_tampering_reject(self):
  m=manifest();r=c.run_owned(m,lambda x:replay(x,"baseline"),lambda x:replay(x,"candidate"),ev);z=r.results[0]
  with self.assertRaises(ValueError):replace(z,baseline=None,identity=c._digest((z.run_id,z.case_id,z.outcome,z.reason,None,z.candidate,z.baseline_observation,z.candidate_observation,z.transitions)))
  with self.assertRaises(ValueError):c.validate_report(m,replace(r,run_id="0"*64,identity="0"*64))
 def test_transitions_all_pairs(self):self.assertEqual((c._transition(False,True),c._transition(True,False),c._transition(True,True),c._transition(False,False),c._transition(None,True)),(c.Transition.IMPROVEMENT,c.Transition.REGRESSION,c.Transition.UNCHANGED_PASS,c.Transition.UNCHANGED_FAIL,c.Transition.NOT_COMPARABLE))
 def test_axis_summaries_all_four_conserve_and_na(self):
  m=manifest(("manager","real-source-unavailable","held-out-unavailable"));r=c.run_owned(m,lambda x:replay(x,"baseline"),lambda x:replay(x,"candidate"),ev);axes=c.summarize(m,r);self.assertEqual(len(axes),4)
  self.assertTrue(any(n is None for a in axes for _,n in a.denominators));self.assertTrue(all(a.total==a.available+a.unavailable for a in axes))
 def test_fixture_positive_and_targeted_negative_controls(self):
  for record in RECORDS:
   m=manifest((record.case_id,));positive=c.run_owned(m,lambda x:replay(x,"baseline"),lambda x:replay(x,"candidate",POSITIVE_CANDIDATES[x.case_id]),fixture_evaluator)
   self.assertTrue(all(value for _,value in positive.results[0].candidate_observation.values),record.case_id)
   answer,metric=NEGATIVE_CANDIDATES[record.case_id];negative=c.run_owned(m,lambda x:replay(x,"baseline"),lambda x:replay(x,"candidate",answer),fixture_evaluator)
   self.assertFalse(dict(negative.results[0].candidate_observation.values)[metric],record.case_id)
 def test_validate_report_rejects_all_eight_rehashed_result_bypasses(self):
  m=manifest();good=c.run_owned(m,lambda x:replay(x,"baseline"),lambda x:replay(x,"candidate"),ev);base=good.results[0];r=m.records[0]
  wrong=replace(base.candidate,artifact_id="wrong",code_id="wrong",stage="wrong");wrongobs=ev(r,wrong,"candidate")
  variants=(
   rebuilt(base,candidate=wrong,candidate_observation=wrongobs),
   rebuilt(base,candidate_observation=replace(base.candidate_observation,expected_record_id="stale-record")),
   rebuilt(base,transitions=tuple((n,c.Transition.REGRESSION if n=="completeness" else v)for n,v in base.transitions)),
   rebuilt(base,outcome=c.Outcome.UNAVAILABLE,reason="unavailable_evidence"),
   rebuilt(base,outcome=c.Outcome.UNAVAILABLE,reason="baseline_unavailable"),
   rebuilt(base,outcome=c.Outcome.UNAVAILABLE,reason="candidate_unavailable"),
   rebuilt(base,outcome=c.Outcome.UNAVAILABLE,reason="evaluator_fault"),
  )
  for bad in variants:
   with self.assertRaises(ValueError):c.validate_report(m,rebuilt_report(m,bad))
  u=manifest(("real-source-unavailable",));ur=c.run_owned(u,lambda x:None,lambda x:None,lambda *x:None).results[0]
  bad=rebuilt(ur,transitions=tuple((n,c.Transition.UNCHANGED_PASS)for n in c.METRICS))
  with self.assertRaises(ValueError):c.validate_report(u,rebuilt_report(u,bad))
