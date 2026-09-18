"""Closed-world, offline V2-05 replay comparison harness."""
from __future__ import annotations
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable
from .contracts import _enum, _tuple_of

METRICS=("correctness_constraint","completeness","false_refusal","unsupported_claim","scope_violation","citation_support","selection_accuracy")
class Provenance(str,Enum): REAL_SOURCE="real_source"; SYNTHETIC="synthetic"
class Split(str,Enum): DEVELOPMENT="development"; RESERVED_HELD_OUT="reserved_held_out"
class Disposition(str,Enum): APPROVED="approved"; UNAVAILABLE="unavailable"
class Outcome(str,Enum): AVAILABLE="available"; UNAVAILABLE="unavailable"
class Transition(str,Enum): IMPROVEMENT="improvement"; REGRESSION="regression"; UNCHANGED_PASS="unchanged_pass"; UNCHANGED_FAIL="unchanged_fail"; NOT_COMPARABLE="not_comparable"

def _text(v,label):
 if not isinstance(v,str):raise ValueError(label+" must be text")
 v=unicodedata.normalize("NFKC",v).strip()
 if not v or "\x00" in v:raise ValueError(label+" blank or malformed")
 return v
def _name(v,label):
 v=_text(v,label)
 if any(c.isspace() for c in v):raise ValueError(label+" whitespace ambiguity")
 return v
def _family(v,label="family"):return " ".join(_text(v,label).casefold().split())
def _hex(v,label="hash"):
 if not isinstance(v,str) or not re.fullmatch(r"[0-9a-f]{64}",v):raise ValueError(label+" lowercase sha256 required")
 return v
def _canon(v):
 """Type/cardinality/byte-length encoding; Enum precedes its str base."""
 if isinstance(v,Enum):return b"E"+_canon(type(v).__qualname__)+_canon(v.value)
 if v is None:return b"N"
 if type(v) is bool:return b"B1" if v else b"B0"
 if type(v) is int:return b"I"+str(v).encode()+b";"
 if isinstance(v,str):
  raw=v.encode();return b"S"+str(len(raw)).encode()+b":"+raw
 if isinstance(v,bytes):return b"Y"+str(len(v)).encode()+b":"+v
 if isinstance(v,tuple):return b"T"+str(len(v)).encode()+b":"+b"".join(_canon(x) for x in v)
 if hasattr(v,"__dataclass_fields__"):return b"D"+_canon(type(v).__qualname__)+_canon(tuple(getattr(v,n) for n in v.__dataclass_fields__))
 raise ValueError("unsupported canonical value")
def _digest(v):return hashlib.sha256(_canon(v)).hexdigest()
def _sha(v):return hashlib.sha256(v).hexdigest()

@dataclass(frozen=True)
class RequestContext:
 request_id:str; original_message:str; current_message:str; turns_identity:str; country:str; directory_country:str; role:str; language:str; effective_version:str
 def __post_init__(self):
  for n in ("request_id","turns_identity","role","language","effective_version"):object.__setattr__(self,n,_name(getattr(self,n),n))
  for n in ("original_message","current_message"):object.__setattr__(self,n,_text(getattr(self,n),n))
  for n in ("country","directory_country"):
   if not isinstance(getattr(self,n),str) or not re.fullmatch(r"[A-Z]{2}",getattr(self,n)):raise ValueError("invalid market")

@dataclass(frozen=True)
class SourceBinding:
 source_id:str; version:str; source_family:str; data:bytes; start:int; end:int; quote:bytes
 def __post_init__(self):
  object.__setattr__(self,"source_id",_name(self.source_id,"source id"));object.__setattr__(self,"version",_name(self.version,"source version"));object.__setattr__(self,"source_family",_family(self.source_family,"source family"))
  if not isinstance(self.data,bytes) or not isinstance(self.quote,bytes) or type(self.start)is not int or type(self.end)is not int or not 0<=self.start<self.end<=len(self.data) or self.data[self.start:self.end]!=self.quote:raise ValueError("source span or quote")
 @property
 def content_hash(self):return _sha(self.data)
 @property
 def identity(self):return _digest((self.source_id,self.version,self.source_family,self.content_hash,self.start,self.end,self.quote))

@dataclass(frozen=True)
class Obligation:
 aspect:str; annotations:tuple[str,...]; alternative_group:str|None=None
 def __post_init__(self):
  object.__setattr__(self,"aspect",_name(self.aspect,"aspect"));vals=tuple(_text(x,"annotation") for x in _tuple_of(self.annotations,str,"annotations"))
  if not vals or len(set(vals))!=len(vals):raise ValueError("empty or duplicate obligation")
  object.__setattr__(self,"annotations",vals)
  if self.alternative_group is not None:object.__setattr__(self,"alternative_group",_name(self.alternative_group,"alternative group"))

@dataclass(frozen=True)
class ReviewedRecord:
 record_id:str; case_id:str; provenance:Provenance; split:Split; family:str; request:RequestContext; source:SourceBinding|None; obligations:tuple[Obligation,...]; expected_constraints:tuple[str,...]; baseline_artifact:str|None; baseline_content:str|None; baseline_code:str|None; candidate_artifact:str|None; candidate_code:str|None; reviewer_id:str|None; disposition:Disposition; unavailable_reason:str|None=None
 def __post_init__(self):
  for n in ("record_id","case_id"):object.__setattr__(self,n,_name(getattr(self,n),n))
  object.__setattr__(self,"provenance",_enum(self.provenance,Provenance,"provenance"));object.__setattr__(self,"split",_enum(self.split,Split,"split"));object.__setattr__(self,"disposition",_enum(self.disposition,Disposition,"disposition"));object.__setattr__(self,"family",_family(self.family))
  if not isinstance(self.request,RequestContext):raise ValueError("typed request")
  obligations=_tuple_of(self.obligations,Obligation,"obligations"); expected=tuple(_text(x,"expected") for x in _tuple_of(self.expected_constraints,str,"expected"))
  if self.disposition is Disposition.APPROVED:
   if not isinstance(self.source,SourceBinding) or not obligations or not expected:raise ValueError("approved authority incomplete")
   for n in ("baseline_artifact","baseline_content","baseline_code","candidate_artifact","candidate_code","reviewer_id"):object.__setattr__(self,n,_name(getattr(self,n),n))
   if self.unavailable_reason is not None:raise ValueError("approved unavailable reason")
  else:
   if self.source is not None or obligations or expected or any(getattr(self,n)is not None for n in ("baseline_artifact","baseline_content","baseline_code","candidate_artifact","candidate_code","reviewer_id")):raise ValueError("unavailable payload")
   object.__setattr__(self,"unavailable_reason",_text(self.unavailable_reason,"unavailable reason"))
  object.__setattr__(self,"obligations",obligations);object.__setattr__(self,"expected_constraints",expected)
 @property
 def identity(self):return _digest((self.record_id,self.case_id,self.provenance,self.split,self.family,self.request,self.source,self.obligations,self.expected_constraints,self.baseline_artifact,self.baseline_content,self.baseline_code,self.candidate_artifact,self.candidate_code,self.reviewer_id,self.disposition,self.unavailable_reason))

@dataclass(frozen=True)
class Authority:
 schema_version:str; registry_version:str; ledger_version:str; records:tuple[ReviewedRecord,...]; ledger_identity:str
 def __post_init__(self):
  for n in ("schema_version","registry_version","ledger_version"):object.__setattr__(self,n,_name(getattr(self,n),n))
  records=_tuple_of(self.records,ReviewedRecord,"records")
  if len({x.record_id for x in records})!=len(records) or len({x.case_id for x in records})!=len(records):raise ValueError("duplicate review authority")
  object.__setattr__(self,"records",records);_hex(self.ledger_identity,"ledger identity")
 @property
 def identity(self):return _digest((self.schema_version,self.registry_version,self.ledger_version,tuple(x.identity for x in self.records),self.ledger_identity))

@dataclass(frozen=True)
class Manifest:
 authority_identity:str; ledger_identity:str; implementation_id:str; evaluator_version:str; comparison_id:str; records:tuple[ReviewedRecord,...]; identity:str
 def __post_init__(self):
  _hex(self.authority_identity,"authority identity");_hex(self.ledger_identity,"ledger identity")
  for n in ("implementation_id","evaluator_version","comparison_id"):object.__setattr__(self,n,_name(getattr(self,n),n))
  records=_tuple_of(self.records,ReviewedRecord,"manifest records")
  if not records or len({x.case_id for x in records})!=len(records):raise ValueError("manifest membership")
  object.__setattr__(self,"records",records)
  if _hex(self.identity,"manifest identity")!=_digest((self.authority_identity,self.ledger_identity,self.implementation_id,self.evaluator_version,self.comparison_id,tuple(x.identity for x in records))):raise ValueError("stale manifest")

@dataclass(frozen=True)
class Replay:
 artifact_id:str; content_id:str; input_id:str; code_id:str; stage:str; answer:str
 def __post_init__(self):
  for n in ("artifact_id","content_id","input_id","code_id","stage"):object.__setattr__(self,n,_name(getattr(self,n),n))
  object.__setattr__(self,"answer",_text(self.answer,"answer"))
  if self.content_id!=_sha(self.answer.encode()):raise ValueError("replay digest")

@dataclass(frozen=True)
class Observation:
 case_id:str; expected_record_id:str; replay_digest:str; side:str; evaluator_version:str; values:tuple[tuple[str,bool],...]
 def __post_init__(self):
  for n in ("case_id","expected_record_id","side","evaluator_version"):object.__setattr__(self,n,_name(getattr(self,n),n))
  _hex(self.replay_digest,"replay digest")
  if self.side not in ("baseline","candidate"):raise ValueError("observation side")
  vals=_tuple_of(self.values,tuple,"observations")
  if len(vals)!=len(METRICS) or {x[0] for x in vals}!=set(METRICS) or any(len(x)!=2 or type(x[1])is not bool for x in vals):raise ValueError("exact boolean metrics")
  object.__setattr__(self,"values",tuple(sorted(vals)))

def _transition(a,b):
 if a is None or b is None:return Transition.NOT_COMPARABLE
 if not a and b:return Transition.IMPROVEMENT
 if a and not b:return Transition.REGRESSION
 return Transition.UNCHANGED_PASS if a else Transition.UNCHANGED_FAIL

@dataclass(frozen=True)
class CaseResult:
 run_id:str; case_id:str; outcome:Outcome; reason:str; baseline:Replay|None; candidate:Replay|None; baseline_observation:Observation|None; candidate_observation:Observation|None; transitions:tuple[tuple[str,Transition],...]; identity:str
 def __post_init__(self):
  _hex(self.run_id,"run identity");object.__setattr__(self,"case_id",_name(self.case_id,"case id"));object.__setattr__(self,"outcome",_enum(self.outcome,Outcome,"outcome"));object.__setattr__(self,"reason",_name(self.reason,"reason"))
  tr=_tuple_of(self.transitions,tuple,"transitions")
  if len(tr)!=len(METRICS) or {x[0]for x in tr}!=set(METRICS) or any(not isinstance(x[1],Transition)for x in tr):raise ValueError("exact transitions")
  object.__setattr__(self,"transitions",tuple(sorted(tr)))
  if self.outcome is Outcome.AVAILABLE:
   if self.reason!="paired" or not all((self.baseline,self.candidate,self.baseline_observation,self.candidate_observation)):raise ValueError("available payload")
  elif self.reason not in ("unavailable_evidence","baseline_unavailable","candidate_unavailable","evaluator_fault"):raise ValueError("unavailable reason")
  if _hex(self.identity,"result identity")!=_digest((self.run_id,self.case_id,self.outcome,self.reason,self.baseline,self.candidate,self.baseline_observation,self.candidate_observation,self.transitions)):raise ValueError("tampered result")

@dataclass(frozen=True)
class AxisSummary:
 provenance:Provenance; split:Split; total:int; available:int; unavailable:int; denominators:tuple[tuple[str,int|None],...]
 def __post_init__(self):
  object.__setattr__(self,"provenance",_enum(self.provenance,Provenance,"provenance"));object.__setattr__(self,"split",_enum(self.split,Split,"split"))
  if any(type(x)is not int or x<0 for x in (self.total,self.available,self.unavailable)) or self.total!=self.available+self.unavailable:raise ValueError("axis conservation")
  d=_tuple_of(self.denominators,tuple,"denominators")
  if len(d)!=len(METRICS) or {x[0]for x in d}!=set(METRICS) or any(x[1]is not None and(type(x[1])is not int or x[1]<0)for x in d):raise ValueError("metric denominators")
  object.__setattr__(self,"denominators",tuple(sorted(d)))

@dataclass(frozen=True)
class Report:
 manifest_identity:str; run_id:str; results:tuple[CaseResult,...]; summaries:tuple[AxisSummary,...]; identity:str
 def __post_init__(self):
  _hex(self.manifest_identity,"manifest identity");_hex(self.run_id,"run identity");results=_tuple_of(self.results,CaseResult,"results");summaries=_tuple_of(self.summaries,AxisSummary,"summaries")
  if len({x.case_id for x in results})!=len(results) or any(x.run_id!=self.run_id for x in results) or {(x.provenance,x.split)for x in summaries}!={(p,s)for p in Provenance for s in Split}:raise ValueError("report membership or axes")
  object.__setattr__(self,"results",results);object.__setattr__(self,"summaries",tuple(sorted(summaries,key=lambda x:(x.provenance.value,x.split.value))))
  if _hex(self.identity,"report identity")!=_digest((self.manifest_identity,self.run_id,tuple(x.identity for x in results),self.summaries)):raise ValueError("tampered report")

def _owned():
 fixture=__import__(__package__+".comparison_fixture",fromlist=("AUTHORITY",));exposure=__import__(__package__+".comparison_exposure",fromlist=("LEDGER_VERSION",))
 authority=fixture.AUTHORITY
 if not isinstance(authority,Authority) or authority.ledger_version!=exposure.LEDGER_VERSION or authority.ledger_identity!=exposure.ledger_identity(authority.records):raise ValueError("owned authority/ledger invalid")
 return authority
def _revalidate(manifest):
 authority=_owned()
 if not isinstance(manifest,Manifest) or manifest.authority_identity!=authority.identity or manifest.ledger_identity!=authority.ledger_identity:raise ValueError("unowned or stale manifest")
 index={x.case_id:x for x in authority.records}
 if tuple(index.get(x.case_id)for x in manifest.records)!=manifest.records:raise ValueError("manifest replacement")
 Manifest(manifest.authority_identity,manifest.ledger_identity,manifest.implementation_id,manifest.evaluator_version,manifest.comparison_id,manifest.records,manifest.identity);return authority
def admit_owned(case_ids:Iterable[str],implementation_id:str,evaluator_version:str,comparison_id:str):
 authority=_owned();ids=_tuple_of(case_ids,str,"case ids")
 if not ids or len(set(ids))!=len(ids):raise ValueError("ordered unique owned cases")
 index={x.case_id:x for x in authority.records}
 try:records=tuple(index[_name(x,"case id")]for x in ids)
 except KeyError as e:raise ValueError("unknown owned case")from e
 ident=_digest((authority.identity,authority.ledger_identity,_name(implementation_id,"implementation"),_name(evaluator_version,"evaluator version"),_name(comparison_id,"comparison id"),tuple(x.identity for x in records)))
 return Manifest(authority.identity,authority.ledger_identity,implementation_id,evaluator_version,comparison_id,records,ident)
def _input(r):return _digest((r.identity,r.request))
def _valid_replay(x,r,side):
 if not isinstance(x,Replay) or r.disposition is not Disposition.APPROVED:return False
 want=(r.baseline_artifact,r.baseline_content,r.baseline_code,"saved_baseline")if side=="baseline"else(r.candidate_artifact,None,r.candidate_code,"deterministic_v2")
 return x.artifact_id==want[0] and x.code_id==want[2] and x.stage==want[3] and x.input_id==_input(r) and(side!="baseline"or x.content_id==want[1])
def _valid_observation(x,r,replay,side,version):return isinstance(x,Observation)and x.case_id==r.case_id and x.expected_record_id==r.record_id and x.replay_digest==replay.content_id and x.side==side and x.evaluator_version==version
def _result(run,r,outcome,reason,b=None,c=None,o=None,n=None):
 om=dict(o.values)if o else{};nm=dict(n.values)if n else{};tr=tuple(sorted((m,_transition(om.get(m),nm.get(m)))for m in METRICS));return CaseResult(run,r.case_id,outcome,reason,b,c,o,n,tr,_digest((run,r.case_id,outcome,reason,b,c,o,n,tr)))
def _validate_result(run,r,result,version):
 """Revalidate an externally retained result against current owned authority."""
 if not isinstance(result,CaseResult) or result.run_id!=run or result.case_id!=r.case_id:raise ValueError("result membership")
 CaseResult(result.run_id,result.case_id,result.outcome,result.reason,result.baseline,result.candidate,result.baseline_observation,result.candidate_observation,result.transitions,result.identity)
 absent=tuple((m,Transition.NOT_COMPARABLE)for m in sorted(METRICS))
 if result.reason=="unavailable_evidence":
  valid=r.disposition is Disposition.UNAVAILABLE and not any((result.baseline,result.candidate,result.baseline_observation,result.candidate_observation)) and result.transitions==absent
 elif result.reason=="baseline_unavailable":
  valid=r.disposition is Disposition.APPROVED and not any((result.baseline,result.candidate,result.baseline_observation,result.candidate_observation)) and result.transitions==absent
 elif result.reason=="candidate_unavailable":
  valid=r.disposition is Disposition.APPROVED and _valid_replay(result.baseline,r,"baseline") and result.candidate is None and result.baseline_observation is None and result.candidate_observation is None and result.transitions==absent
 elif result.reason=="evaluator_fault":
  valid=r.disposition is Disposition.APPROVED and _valid_replay(result.baseline,r,"baseline") and _valid_replay(result.candidate,r,"candidate") and result.baseline_observation is None and result.candidate_observation is None and result.transitions==absent
 elif result.reason=="paired":
  valid=r.disposition is Disposition.APPROVED and _valid_replay(result.baseline,r,"baseline") and _valid_replay(result.candidate,r,"candidate") and _valid_observation(result.baseline_observation,r,result.baseline,"baseline",version) and _valid_observation(result.candidate_observation,r,result.candidate,"candidate",version)
  if valid:
   old=dict(result.baseline_observation.values);new=dict(result.candidate_observation.values);valid=result.transitions==tuple(sorted((m,_transition(old[m],new[m]))for m in METRICS))
 else: valid=False
 if not valid or (result.reason=="paired") != (result.outcome is Outcome.AVAILABLE):raise ValueError("owned result invariant")
 return result
def _summaries(records,results):
 index={x.case_id:x for x in records};out=[]
 for p in Provenance:
  for s in Split:
   chosen=[x for x in results if index[x.case_id].provenance is p and index[x.case_id].split is s];avail=[x for x in chosen if x.outcome is Outcome.AVAILABLE]
   out.append(AxisSummary(p,s,len(chosen),len(avail),len(chosen)-len(avail),tuple((m,len(avail)if avail else None)for m in METRICS)))
 return tuple(out)
def _run_id(m):return _digest((m.identity,tuple((x.case_id,x.baseline_artifact,x.baseline_content,x.baseline_code,x.candidate_artifact,x.candidate_code)for x in m.records),m.evaluator_version,m.comparison_id))
def run_owned(manifest:Manifest,baseline:Callable,candidate:Callable,evaluator:Callable):
 _revalidate(manifest)
 if not all(callable(x)for x in (baseline,candidate,evaluator)):raise ValueError("injected adapters")
 run=_run_id(manifest);results=[]
 for r in manifest.records:
  if r.disposition is Disposition.UNAVAILABLE:results.append(_validate_result(run,r,_result(run,r,Outcome.UNAVAILABLE,"unavailable_evidence"),manifest.evaluator_version));continue
  try:b=baseline(r)
  except Exception:b=None
  if not _valid_replay(b,r,"baseline"):results.append(_validate_result(run,r,_result(run,r,Outcome.UNAVAILABLE,"baseline_unavailable"),manifest.evaluator_version));continue
  try:c=candidate(r)
  except Exception:c=None
  if not _valid_replay(c,r,"candidate"):results.append(_validate_result(run,r,_result(run,r,Outcome.UNAVAILABLE,"candidate_unavailable",b),manifest.evaluator_version));continue
  try:o=evaluator(r,b,"baseline");n=evaluator(r,c,"candidate")
  except Exception:o=n=None
  if not _valid_observation(o,r,b,"baseline",manifest.evaluator_version)or not _valid_observation(n,r,c,"candidate",manifest.evaluator_version):results.append(_validate_result(run,r,_result(run,r,Outcome.UNAVAILABLE,"evaluator_fault",b,c),manifest.evaluator_version));continue
  results.append(_validate_result(run,r,_result(run,r,Outcome.AVAILABLE,"paired",b,c,o,n),manifest.evaluator_version))
 results=tuple(results);summary=_summaries(manifest.records,results);return Report(manifest.identity,run,results,summary,_digest((manifest.identity,run,tuple(x.identity for x in results),tuple(sorted(summary,key=lambda x:(x.provenance.value,x.split.value))))))
def validate_report(manifest:Manifest,report:Report):
 _revalidate(manifest)
 if not isinstance(report,Report)or report.manifest_identity!=manifest.identity or report.run_id!=_run_id(manifest)or tuple(x.case_id for x in report.results)!=tuple(x.case_id for x in manifest.records):raise ValueError("stale report")
 index={x.case_id:x for x in manifest.records}
 for x in report.results:_validate_result(report.run_id,index[x.case_id],x,manifest.evaluator_version)
 expected=tuple(sorted(_summaries(manifest.records,report.results),key=lambda x:(x.provenance.value,x.split.value)))
 if report.summaries!=expected:raise ValueError("summary mismatch")
 Report(report.manifest_identity,report.run_id,report.results,report.summaries,report.identity);return report
def summarize(manifest:Manifest,report:Report):return validate_report(manifest,report).summaries
