from __future__ import annotations
from pathlib import Path
import unittest
from app.experimental.evidence_first_v2 import audit
ROOT=Path(__file__).resolve().parents[2]
def manifest():return tuple((p,(ROOT/p).read_bytes()) for p,_ in audit.APPROVED_FILES)
class AuditTests(unittest.TestCase):
 def test_closed_26_path_manifest_and_aggregates(self):
  x=manifest();self.assertEqual(len(x),26);self.assertTrue(audit.verify_approved(x,audit.ACCEPTED_AGGREGATES))
  for bad in (x[:-1],x+(("extra.py",b"x"),),tuple(reversed(x)),x[:1]+((x[0][0].replace("contracts.py","../contracts.py"),x[0][1]),)+x[1:]):self.assertFalse(audit.verify_approved(bad,audit.ACCEPTED_AGGREGATES))
  self.assertFalse(audit.verify_approved(x,audit.ACCEPTED_AGGREGATES[:-1]))
 def test_manifest_drift_duplicate_and_public_alias_do_not_authorize(self):
  x=list(manifest());x[0]=(x[0][0],b"drift");self.assertFalse(audit.verify_approved(tuple(x),audit.ACCEPTED_AGGREGATES))
  original=manifest();old=audit.APPROVED_FILES
  try:audit.APPROVED_FILES=();self.assertTrue(audit.verify_approved(original,audit.ACCEPTED_AGGREGATES))
  finally:audit.APPROVED_FILES=old
 def test_closed_adapter_schemas(self):
  self.assertEqual(tuple(x.stage for x in audit.INTEGRATION_CONTRACT),audit.STAGES)
  for args in (("x","a","b",("x",)),("interpret","a","b",("",)),("interpret","request_context","standalone_request",("x","x"))):
   with self.assertRaises(ValueError):audit.AdapterContract(*args)
 def test_executed_accounting_conserves_and_skips_after_fault(self):
  calls=[]
  def adapter(stage):return lambda case:(calls.append((case,stage)) or ("fault" if (case,stage)==("fault","ground") else "completed"))
  x=audit.execute_offline(("hit","fault"),tuple((s,adapter(s)) for s in audit.STAGES))
  self.assertEqual(x.total,len(calls));self.assertEqual(x.stage("compare_rank"),1);self.assertEqual(x.records[1].stages[3].skipped,1)
  with self.assertRaises(ValueError):audit.execute_offline((),())
 def test_cutover_budget_unavailable_and_isolation_spec(self):
  self.assertEqual(audit.CUTOVER.owner,"APPROVAL_REQUIRED");self.assertTrue(audit.CUTOVER.recovery_checks);self.assertIn("monetary_cost",audit.UNAVAILABLE);self.assertIn("billable_units_currency_time",audit.APPROVAL_CHECKLIST)
  text=(ROOT/"app/experimental/evidence_first_v2/audit.py").read_text(encoding="utf-8");self.assertNotIn("app.retrieval",text);self.assertNotIn("boto3",text)
 def test_nonexperimental_production_scope_is_unreferenced(self):
  files=[p for p in (ROOT/"app").rglob("*.py") if "experimental" not in p.parts];self.assertGreaterEqual(len(files),114)
  for p in files:self.assertNotIn("evidence_first_v2",p.read_text(encoding="utf-8"),str(p))
 def test_historical_authority_is_recomputed_not_accepted_by_label(self):
  self.assertEqual(audit._historical_aggregates(),audit.ACCEPTED_AGGREGATES)
  self.assertEqual(len(audit._MILESTONE_MANIFESTS),6)
  self.assertEqual(len(audit._MILESTONE_SERIALIZATIONS),6)
  self.assertEqual(len(audit._SUPERSESSION),2)
  bad=list(audit.ACCEPTED_AGGREGATES);bad[0]="0"*64
  self.assertFalse(audit.verify_approved(manifest(),tuple(bad)))
 def test_exact_record_types_and_terminal_truth_table(self):
  class S(str):pass
  for outcome,counts in audit._COUNTERS.items():
   self.assertEqual(audit.StageRecord("interpret",*counts,outcome).outcome,outcome)
  for args in (("interpret",0,1,0,0,0,"completed"),("interpret",1,0,0,1,0,"completed"),("interpret",0,0,1,0,0,"completed"),("interpret",1,1,0,0,1,"retried"),("interpret",1,1,0,0,0,S("completed"))):
   with self.assertRaises(ValueError):audit.StageRecord(*args)
  row=audit.CaseRecord("case",tuple(audit.StageRecord(stage,*audit._COUNTERS["completed"],"completed") for stage in audit.STAGES))
  with self.assertRaises(ValueError):audit.CallCounts((object(),))
  with self.assertRaises(ValueError):audit.CaseRecord(" case",row.stages)
 def test_every_terminal_outcome_and_rank_eligibility(self):
  for terminal in ("missing","fault","cancelled","corrected","retried"):
   calls=[]
   def adapter(stage):
    def run(case):
     calls.append(stage)
     if stage=="ground":return "completed" if calls.count(stage)>1 else terminal
     return "completed"
    return run
   result=audit.execute_offline((terminal,),tuple((stage,adapter(stage)) for stage in audit.STAGES))
   record=result.records[0]
   expected_calls=4 if terminal in ("corrected","retried") else 3
   self.assertEqual(len(calls),expected_calls)
   self.assertEqual(record.stages[2].outcome,terminal)
   self.assertFalse(record.rank_eligible)
   self.assertTrue(all(stage.outcome=="skipped" for stage in record.stages[3:]))
  self.assertTrue(audit.execute_offline(("hit",),tuple((stage,lambda case:"completed") for stage in audit.STAGES)).records[0].rank_eligible)
 def test_adapter_exception_is_sanitized_fault_and_stops_downstream(self):
  calls=[]
  def boom(case):
   calls.append(case);raise RuntimeError("private adapter detail")
  result=audit.execute_offline(("case",),(("interpret",lambda case:"completed"),("retrieve",boom),("ground",lambda case:"completed"),("compose_validate",lambda case:"completed"),("compare_rank",lambda case:"completed")))
  self.assertEqual(calls,["case"])
  self.assertEqual(result.records[0].stages[1].outcome,"fault")
  self.assertEqual(result.records[0].stages[2].attempted,0)
 def test_failed_retry_conserves_its_second_actual_attempt(self):
  seen=[]
  def ground(case):
   seen.append(case);return "retried" if len(seen)==1 else "fault"
  result=audit.execute_offline(("case",),(("interpret",lambda case:"completed"),("retrieve",lambda case:"completed"),("ground",ground),("compose_validate",lambda case:"completed"),("compare_rank",lambda case:"completed")))
  stage=result.records[0].stages[2]
  self.assertEqual((len(seen),stage.attempted,stage.retry,stage.fault,stage.outcome),(2,2,1,1,"fault"))
 def test_cutover_trigger_window_and_strict_scalars(self):
  self.assertEqual(audit.CUTOVER.trigger,"APPROVAL_REQUIRED")
  self.assertEqual(audit.CUTOVER.observation_window,"APPROVAL_REQUIRED")
  with self.assertRaises(ValueError):audit.CutoverSpec("x","x","x","","x","x","x",("x",),"x")
 def test_malformed_historical_authority_fails_closed_without_zip_truncation(self):
  original=(audit._MILESTONE_MANIFESTS,audit._MILESTONE_SERIALIZATIONS)
  cases=((audit._MILESTONE_MANIFESTS[:-1],audit._MILESTONE_SERIALIZATIONS),
         (audit._MILESTONE_MANIFESTS+(audit._MILESTONE_MANIFESTS[0],),audit._MILESTONE_SERIALIZATIONS),
         (audit._MILESTONE_MANIFESTS,audit._MILESTONE_SERIALIZATIONS[:-1]),
         (audit._MILESTONE_MANIFESTS,audit._MILESTONE_SERIALIZATIONS+(audit._MILESTONE_SERIALIZATIONS[0],)),
         ((((("path",),)+audit._MILESTONE_MANIFESTS[0][1:],)+audit._MILESTONE_MANIFESTS[1:]),audit._MILESTONE_SERIALIZATIONS),
         (((((1,"0"*64),)+audit._MILESTONE_MANIFESTS[0][1:],)+audit._MILESTONE_MANIFESTS[1:]),audit._MILESTONE_SERIALIZATIONS),
         ((((("path",1),)+audit._MILESTONE_MANIFESTS[0][1:],)+audit._MILESTONE_MANIFESTS[1:]),audit._MILESTONE_SERIALIZATIONS),
         (audit._MILESTONE_MANIFESTS,(("backslash",),)+audit._MILESTONE_SERIALIZATIONS[1:]))
  try:
   for manifests,rules in cases:
    audit._MILESTONE_MANIFESTS,audit._MILESTONE_SERIALIZATIONS=manifests,rules
    self.assertFalse(audit.verify_approved(manifest(),audit.ACCEPTED_AGGREGATES))
  finally:audit._MILESTONE_MANIFESTS,audit._MILESTONE_SERIALIZATIONS=original
 def test_all_32_serialization_rule_scalar_substitutions_fail_closed(self):
  class StrSub(str):pass
  original=audit._MILESTONE_SERIALIZATIONS; mutations=[]
  for index,rule in enumerate(original):
   for replacement in ((StrSub(rule[0]),rule[1],rule[2],rule[3]),(rule[0],StrSub(rule[1]),rule[2],rule[3]),(rule[0],rule[1],float(rule[2]),rule[3]),(rule[0],rule[1],rule[2],int(rule[3])),(rule[0],rule[1],rule[2],float(rule[3]))):
    changed=list(original);changed[index]=replacement;mutations.append(tuple(changed))
  for index in (0,1):
   changed=list(original);rule=changed[index];changed[index]=(rule[0],rule[1],True,rule[3]);mutations.append(tuple(changed))
  self.assertEqual(len(mutations),32)
  try:
   for rules in mutations:
    audit._MILESTONE_SERIALIZATIONS=rules
    self.assertFalse(audit.verify_approved(manifest(),audit.ACCEPTED_AGGREGATES))
  finally:audit._MILESTONE_SERIALIZATIONS=original
 def test_case_transitions_and_rank_eligibility_are_distinct(self):
  complete=lambda stage:audit.StageRecord(stage,*audit._COUNTERS["completed"],"completed")
  for outcome in ("missing","fault","cancelled","corrected","retried"):
   for index in range(4):
    stages=[complete(stage) for stage in audit.STAGES];stages[index]=audit.StageRecord(audit.STAGES[index],*audit._COUNTERS[outcome],outcome)
    with self.assertRaises(ValueError):audit.CaseRecord("case",tuple(stages))
  stages=tuple(complete(stage) for stage in audit.STAGES[:-1])+(audit.StageRecord("compare_rank",*audit._COUNTERS["fault"],"fault"),)
  record=audit.CaseRecord("case",stages)
  self.assertTrue(record.rank_eligible)
 def test_population_is_prevalidated_and_invoked_skips_are_counted_faults(self):
  calls=[]
  adapters=tuple((stage,lambda case:calls.append(case) or "completed") for stage in audit.STAGES)
  for cases in (("valid"," "),("dup","dup"),("valid",str("bad"))):
   if cases[1]=="bad":cases=("valid",type("StrSub",(str,),{})("bad"))
   with self.assertRaises(ValueError):audit.execute_offline(cases,adapters)
   self.assertEqual(calls,[])
  for target in audit.STAGES:
   invoked=[]
   def adapter(stage):
    return lambda case:(invoked.append(stage) or ("skipped" if stage==target else "completed"))
   result=audit.execute_offline(("case",),tuple((stage,adapter(stage)) for stage in audit.STAGES))
   row=next(item for item in result.records[0].stages if item.stage==target)
   self.assertEqual((row.outcome,row.attempted), ("fault",1))
   self.assertEqual(invoked.count(target),1)
 def test_cutover_rejects_whitespace_and_untrimmed_values_everywhere(self):
  values=["owner","executor","escalation","trigger","window","flag","traffic",("check",),"reenable"]
  for index in range(8):
   changed=list(values);changed[index]=" x "
   with self.assertRaises(ValueError):audit.CutoverSpec(*changed)
  for value in (" "," check "):
   with self.assertRaises(ValueError):audit.CutoverSpec("owner","executor","escalation","trigger","window","flag","traffic",(value,),"reenable")
