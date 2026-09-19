"""V2-07 closed offline audit and future specification; no production wiring."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass

# Private historical authority: exact accepted path/hash order for each milestone.
_MILESTONE_MANIFESTS = (
 (("app/experimental/evidence_first_v2/__init__.py","13403beee86c359557db9879d72cd4f5fb626e692539c3aef336ffbb9fe71c70"),("app/experimental/evidence_first_v2/contracts.py","54ace657e67ec7a5d4751ea3ee8f8af40bda65ff43f14d59f29adc61cd76f571"),("app/experimental/evidence_first_v2/scope.py","3bd8786c074e17ebe2acc5e7d37ae5daa29dcce786c868fe9fc6497eea980c11"),("tests/evidence_first_v2/test_contracts_and_scope.py","17f7dadebcf33176ae917f805733081d9723074088509263ff5145d5ac74bf34"),("tests/evidence_first_v2/test_offline_isolation.py","9d523358e7cec0446e1bdc4a7796bbb52d396a8d7f1fdf69d7fbece3d0ed4b0d"),("docs/evidence_first_v2/V2-01-contracts.md","4ebb3129dda0013ab4c156ebd2c5d5a8c3165b34eeb4ff5afd2012bc79e825b1")),
 (("app/experimental/evidence_first_v2/__init__.py","bf407ecb98e4236d63dba4e2503a7845af78ffa20cb79ca8812ee8759990801a"),("app/experimental/evidence_first_v2/context.py","9e01381f5bb3099aa014f8dd9ba7fbe2e7036d08f85955d39967e9e77615e715"),("app/experimental/evidence_first_v2/standalone.py","7083d22080b7fa397145d332275192fbbaacedeedbbf69d7acfa0a1e1e445ead"),("tests/evidence_first_v2/test_offline_isolation.py","0cbcac336a5c847d588e8d6b14870866ad2d509d9fee7ed99fda099a00bed25b"),("tests/evidence_first_v2/test_standalone_request.py","95ed6d7ddb9f995dd42ee94120f5fd8a53b1d0d5eddcffbeda233d6b9bd7ec30"),("docs/evidence_first_v2/V2-02-standalone-request.md","72efabd1ad2d2b560310b03ff1104f880885dff66f516aebbe2f81276945392d")),
 (("app/experimental/evidence_first_v2/evidence.py","9f4047bb0c9e02dfce4d15e60050f16b9f1401c844221694f8847918049f1034"),("tests/evidence_first_v2/test_evidence_facts.py","230e6ae1106166fd2500a9eb515d296432f5b614b610a897dddbc16d168b0b5c"),("docs/evidence_first_v2/V2-03-evidence-facts-and-coverage.md","7d6fada481a69ab79271e7bc287ce5afb645422d11c45948ecb8e014aadb0666")),
 (("app/experimental/evidence_first_v2/orchestration.py","2ea3dc9faaeaee98714261a9285d65d3df890bffe5d03446afd6dc5048f83b81"),("tests/evidence_first_v2/test_orchestration.py","8351e6f4a6955467f6c35efc7f402e6c0b4767da4ca675364b8a4b0f65e5fd3c"),("docs/evidence_first_v2/V2-04-composition-and-validation.md","ca148a2243ca92d92efe9890284b95caf5995c7415d322f23d3e9a01abb87c35")),
 (("app/experimental/evidence_first_v2/comparison.py","fe22b5d3f7fb2f03676ea4ed361d2a64e2d62e42009ef3d2fd97580cb469fb8b"),("app/experimental/evidence_first_v2/comparison_fixture.py","01ebb64300133d04cfcae079e171a59111c9a812f26adf13c28304ebbbf3dcc0"),("app/experimental/evidence_first_v2/comparison_exposure.py","7634212ee743b4e627937eb98f4706fc22c7c742de818a019c5a49a25212dbfc"),("tests/evidence_first_v2/test_comparison.py","7e3d49dada89be247a7a4061fcb5a09b41caccb60992720bef7fa3af6cf5d012"),("docs/evidence_first_v2/V2-05-offline-comparison.md","ae2fa1e852b1af098bdded81b89aaa8931da23bc9ecb18868dea2b925cca2e86")),
 (("app/experimental/evidence_first_v2/ranking.py","b4d2d802a0d968cae2faeaefbcc3bc87157d2c4e3327c5353a23747f95d0f971"),("app/experimental/evidence_first_v2/ranking_fixture.py","b63ba3f52f2f320702aa5084059f43cf98b9e3a26899af98c8a1995464d93523"),("app/experimental/evidence_first_v2/ranking_ledger.py","67cc895d059a802faec088a58686f53364c41eb760490ecbdf4bcda643b5473f"),("tests/evidence_first_v2/test_ranking.py","e472b3b673ba08e6ee101635cf7d972f2f9f74d36cc01418bcc5361b5ac8da26"),("docs/evidence_first_v2/V2-06-offline-ranking.md","39ef95d334c246170dc2cac8c9daf7b2ab7daae22ba9e7518e434f9bf4814aea")),
 (("tests/evidence_first_v2/test_offline_isolation.py","763487c5100d6bc77aedfbd69c65193ec17118ad42862b2e8a623a4298718dc4"),("docs/evidence_first_v2/V2-11-isolation-allowlist-milestone.md","ef70e345e6ac27e51265bfd20823a1dff259bc670acb39f9b7575becae9724f0")),
)
# (path rendering, row order, spaces, final LF), retained as historical serialization rules.
_MILESTONE_SERIALIZATIONS=(("backslash","path_hash",1,False),("backslash","path_hash",1,False),("candidate_forward","hash_path",2,False),("forward","hash_path",2,False),("forward","hash_path",2,True),("forward","hash_path",2,True),("forward","hash_path",2,True))
_ACCEPTED_AGGREGATES=("2afe5baa9d36f70bbed00d2620f864d783298a356bc2c773eb89d286cd8c14d4","d1702e1aea485a7871e9bdb475a4af61442f4e51d7bb12241d7e1d2eb382c1af","ce680472590455d82f3f933d028f344d7e2b07db694afe5a680af3c2e100809e","17bee0133edef910dddb92edd9b89709756a2d6d4605b36b73bf6ddb99edcf8e","b0075ecd31e25395b8c51b57db6a8cf5aad8183fb3dc77d84993efd2fc75999c","e4dbcb64540bf400631050559dff011841004650253b377e41534054935cce3a","2dbe29b1fcadfda68a9655e307aa0fe6de4e2507f9d66a8e53b4341852a9c3c4")
# V2-02 replacements explicitly supersede these V2-01 accepted bytes.
_SUPERSESSION=(("V2-01","V2-02","app/experimental/evidence_first_v2/__init__.py","13403beee86c359557db9879d72cd4f5fb626e692539c3aef336ffbb9fe71c70","bf407ecb98e4236d63dba4e2503a7845af78ffa20cb79ca8812ee8759990801a"),("V2-01","V2-02","tests/evidence_first_v2/test_offline_isolation.py","9d523358e7cec0446e1bdc4a7796bbb52d396a8d7f1fdf69d7fbece3d0ed4b0d","0cbcac336a5c847d588e8d6b14870866ad2d509d9fee7ed99fda099a00bed25b"),("V2-02","V2-11","tests/evidence_first_v2/test_offline_isolation.py","0cbcac336a5c847d588e8d6b14870866ad2d509d9fee7ed99fda099a00bed25b","763487c5100d6bc77aedfbd69c65193ec17118ad42862b2e8a623a4298718dc4"))
_ROWS=tuple(dict(tuple(row for manifest in _MILESTONE_MANIFESTS for row in manifest)).items())
APPROVED_FILES=_ROWS
ACCEPTED_AGGREGATES=_ACCEPTED_AGGREGATES

_MANIFEST_LENGTHS=(6,6,3,3,5,5,2)
_SERIALIZATION_RULES=(("backslash","path_hash",1,False),("backslash","path_hash",1,False),("candidate_forward","hash_path",2,False),("forward","hash_path",2,False),("forward","hash_path",2,True),("forward","hash_path",2,True),("forward","hash_path",2,True))
def _valid_historical_authority(manifests,serializations):
 if type(manifests)is not tuple or type(serializations)is not tuple or len(manifests)!=7 or len(serializations)!=7:return False
 for manifest,rule,size,expected_rule in zip(manifests,serializations,_MANIFEST_LENGTHS,_SERIALIZATION_RULES):
  if type(manifest)is not tuple or len(manifest)!=size or type(rule)is not tuple or len(rule)!=4:return False
  style,order,spaces,final=rule
  if type(style)is not str or type(order)is not str or type(spaces)is not int or type(final)is not bool or rule!=expected_rule:return False
  for row in manifest:
   if type(row)is not tuple or len(row)!=2 or type(row[0])is not str or type(row[1])is not str or not _valid_path(row[0]) or len(row[1])!=64 or any(char not in "0123456789abcdef" for char in row[1]):return False
 return True
def _serialize(manifest,rule):
 style,order,spaces,final=rule; rows=[]
 for path,digest in manifest:
  rendered=path.replace("/","\\") if style=="backslash" else ("askvera-evidence-first-v2/"+path if style=="candidate_forward" else path)
  rows.append(rendered+" "*spaces+digest if order=="path_hash" else digest+" "*spaces+rendered)
 return ("\n".join(rows)+("\n" if final else "")).encode("utf-8")

def _historical_aggregates():
 if not _valid_historical_authority(_MILESTONE_MANIFESTS,_MILESTONE_SERIALIZATIONS):return None
 return tuple(hashlib.sha256(_serialize(manifest,rule)).hexdigest() for manifest,rule in zip(_MILESTONE_MANIFESTS,_MILESTONE_SERIALIZATIONS))
def _valid_path(path):return type(path)is str and path and "\\" not in path and ".." not in path.split("/") and path==path.strip()
def verify_approved(content,aggregates):
 """Validate exact current bytes plus all independently recomputed accepted history."""
 historical=_historical_aggregates()
 if type(content)is not tuple or type(aggregates)is not tuple or historical is None or historical!=_ACCEPTED_AGGREGATES or aggregates!=historical:return False
 if len(content)!=len(_ROWS) or tuple(row[0] for row in content)!=tuple(row[0] for row in _ROWS):return False
 return all(type(path)is str and _valid_path(path) and type(data)is bytes and path==expected and hashlib.sha256(data).hexdigest()==digest for (path,data),(expected,digest) in zip(content,_ROWS))

_SCHEMAS=(("interpret","request_context","standalone_request",("request_id","session_id","policy_market","directory_country","role","language")),("retrieve","standalone_request","candidate_capture",("source_id","corpus_version","index_generation","analyzer_identity")),("ground","candidate_capture","facts_coverage",("witnesses","coverage","missing_evidence")),("compose_validate","facts_coverage","validated_result",("citations","safety","correction","fault")),("compare_rank","validated_result","comparison_ranking_report",("replay_identity","ledger_identity","strategy_parameters","ranking_location")))
@dataclass(frozen=True)
class AdapterContract:
 stage:str; input_type:str; output_type:str; required_bindings:tuple[str,...]
 def __post_init__(self):
  expected=next((item for item in _SCHEMAS if item[0]==self.stage),None)
  if any(type(item)is not str or not item for item in (self.stage,self.input_type,self.output_type)) or expected is None or type(self.required_bindings)is not tuple or (self.stage,self.input_type,self.output_type,self.required_bindings)!=expected or any(type(item)is not str or not item for item in self.required_bindings) or len(set(self.required_bindings))!=len(self.required_bindings):raise ValueError("adapter contract")
INTEGRATION_CONTRACT=tuple(AdapterContract(*schema) for schema in _SCHEMAS)
STAGES=("interpret","retrieve","ground","compose_validate","compare_rank")
OUTCOMES=("completed","missing","fault","cancelled","corrected","skipped","retried")
_COUNTERS={"completed":(1,1,0,0,0),"missing":(1,0,0,0,0),"fault":(1,0,0,1,0),"cancelled":(1,0,0,0,0),"corrected":(2,1,0,0,1),"skipped":(0,0,1,0,0),"retried":(2,1,0,0,1)}
def _valid_counters(outcome,attempted,completed,skipped,fault,retry):
 if outcome=="completed":return attempted==retry+1 and completed==1 and skipped==fault==0
 if outcome=="fault":return attempted==retry+1 and fault==1 and completed==skipped==0
 return (attempted,completed,skipped,fault,retry)==_COUNTERS[outcome]
@dataclass(frozen=True)
class StageRecord:
 stage:str; attempted:int; completed:int; skipped:int; fault:int; retry:int; outcome:str="completed"
 def __post_init__(self):
  if type(self.stage)is not str or self.stage not in STAGES or type(self.outcome)is not str or self.outcome not in OUTCOMES or any(type(getattr(self,name))is not int or getattr(self,name)<0 for name in ("attempted","completed","skipped","fault","retry")) or not _valid_counters(self.outcome,self.attempted,self.completed,self.skipped,self.fault,self.retry):raise ValueError("stage record")
@dataclass(frozen=True)
class CaseRecord:
 case_id:str; stages:tuple[StageRecord,...]
 def __post_init__(self):
  if type(self.case_id)is not str or not self.case_id or self.case_id!=self.case_id.strip() or type(self.stages)is not tuple or not all(type(item)is StageRecord for item in self.stages) or tuple(item.stage for item in self.stages)!=STAGES:raise ValueError("case record")
  stopped=False
  for item in self.stages:
   if stopped and item.outcome!="skipped":raise ValueError("case record")
   stopped=stopped or item.outcome!="completed"
 @property
 def rank_eligible(self):return all(item.outcome=="completed" for item in self.stages[:-1])
@dataclass(frozen=True)
class CallCounts:
 records:tuple[CaseRecord,...]
 def __post_init__(self):
  if type(self.records)is not tuple or not all(type(item)is CaseRecord for item in self.records) or len({item.case_id for item in self.records})!=len(self.records):raise ValueError("counts")
 def stage(self,name):
  if type(name)is not str or name not in STAGES:raise ValueError("stage")
  return sum(next(item.attempted for item in row.stages if item.stage==name) for row in self.records)
 @property
 def total(self):return sum(self.stage(name) for name in STAGES)
def _record(stage,outcome,retry=0):
 values=(1+retry,0,0,1,retry) if outcome=="fault" and retry else _COUNTERS[outcome]
 return StageRecord(stage,*values,outcome)
def _adapter_outcome(adapter,case):
 try:value=adapter(case)
 except Exception:return "fault"
 return value if type(value)is str and value in OUTCOMES and value!="skipped" else "fault"
def execute_offline(cases,adapters):
 """Run injected adapters only; bounded exceptions become sanitized fault records."""
 if type(cases)is not tuple or type(adapters)is not tuple or len(adapters)!=len(STAGES) or any(type(item)is not tuple or len(item)!=2 or type(item[0])is not str or item[0]!=stage or not callable(item[1]) for item,stage in zip(adapters,STAGES)):raise ValueError("execution input")
 if any(type(case)is not str or not case or case!=case.strip() for case in cases) or len(set(cases))!=len(cases):raise ValueError("case")
 rows=[]
 for case in cases:
  enabled=True; records=[]
  for stage,adapter in adapters:
   if not enabled:records.append(_record(stage,"skipped"));continue
   outcome=_adapter_outcome(adapter,case)
   retried=outcome in ("corrected","retried")
   if retried and _adapter_outcome(adapter,case)!="completed":outcome="fault"
   records.append(_record(stage,outcome,1 if retried and outcome=="fault" else 0)); enabled=outcome=="completed"
  rows.append(CaseRecord(case,tuple(records)))
 return CallCounts(tuple(rows))
@dataclass(frozen=True)
class CutoverSpec:
 owner:str; executor:str; escalation:str; trigger:str; observation_window:str; feature_flag:str; traffic_action:str; recovery_checks:tuple[str,...]; reenable_authority:str
 def __post_init__(self):
  if any(type(item)is not str or not item or item!=item.strip() for item in (self.owner,self.executor,self.escalation,self.trigger,self.observation_window,self.feature_flag,self.traffic_action,self.reenable_authority)) or type(self.recovery_checks)is not tuple or not self.recovery_checks or any(type(item)is not str or not item or item!=item.strip() for item in self.recovery_checks):raise ValueError("cutover")
CUTOVER=CutoverSpec("APPROVAL_REQUIRED","APPROVAL_REQUIRED","APPROVAL_REQUIRED","APPROVAL_REQUIRED","APPROVAL_REQUIRED","evidence_first_v2_shadow","shadow:disable flag; traffic:restore existing route",("flag_or_route_restored","existing_path_serving","safety_scope_citation_baseline_recovered","captures_retained_for_approved_review"),"APPROVAL_REQUIRED")
UNAVAILABLE=("real_source_comparison","held_out_comparison","real_ranking_evidence","live_provider","live_index","embedding","generation","latency","monetary_cost")
APPROVAL_CHECKLIST=("data_scope_query_ids","environment_index_generation","paired_arm_stage_retry_failure_inclusions","billable_units_currency_time","owner_executor_escalation_trigger_window","retention_redaction","no_writes_reindex_deploy","recovery_reenable_authority")
