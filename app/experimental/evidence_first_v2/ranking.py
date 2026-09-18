"""Closed, application-owned V2-06 structural ranking experiment."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from enum import Enum

SCHEMA="askvera.saved-candidates.v2"; CHANNELS=("text","vector")
AXES=(("synthetic","development"),("synthetic","held_out"),("real","development"),("real","held_out"))
APPROVED_MARKETS=("US","KE","BE","SE","FI","KG","AT","CH","DE")
_PINNED_APPROVED_MARKETS=APPROVED_MARKETS
APPROVED_ANALYZERS=(("text","unicode-word-v1"),("vector","embedding-offline-v1"))
_PINNED_ANALYZERS=APPROVED_ANALYZERS
ANALYZER_CONTENT_ID="v2-06-analyzers-1"
_PINNED_ANALYZER_CONTENT_ID=ANALYZER_CONTENT_ID
def _approved_analyzer(name):return next(value for channel,value in _PINNED_ANALYZERS if channel==name)
def _digest(x): return hashlib.sha256(repr(x).encode("utf-8")).hexdigest()
def _text(x,n):
 if not isinstance(x,str) or not (x:=x.strip()): raise ValueError(n)
 return x
def _count(x,n):
 if type(x) is not int or x<0: raise ValueError(n)
 return x
def _reason(x):
 x=_text(x,"reason")
 if len(x)>64 or not x.replace("_","").replace("-","").isalnum(): raise ValueError("typed reason")
 return x
def _market(x):
 x=_text(x,"market")
 if len(x)!=2 or not x.isascii() or not x.isupper() or not x.isalpha() or x not in _PINNED_APPROVED_MARKETS: raise ValueError("market")
 return x
def _finite(x): return x==x and x not in (float("inf"),float("-inf"))
def _number(x):
 if type(x) not in (int,float) or not _finite(x): raise ValueError("finite score")
 return float(x)
class Strategy(str,Enum): CURRENT="current"; NORMALIZED="normalized"; RRF="rrf"
class State(str,Enum): COMPLETED="completed"; UNAVAILABLE="unavailable"; REJECTED="rejected"

@dataclass(frozen=True)
class Scope:
 policy_market:str; directory_country:str|None; role:str; query_locale:str; internal_access_allowed:bool=False
 def __post_init__(self):
  object.__setattr__(self,"policy_market",_market(self.policy_market))
  if self.directory_country is not None: object.__setattr__(self,"directory_country",_market(self.directory_country))
  object.__setattr__(self,"role",_text(self.role,"role")); object.__setattr__(self,"query_locale",_text(self.query_locale,"locale"))
  if type(self.internal_access_allowed)is not bool:raise ValueError("access entitlement")
@dataclass(frozen=True)
class ChannelConfig:
 name:str; depth:int; status:str; analyzer:str; analyzer_content_id:str=ANALYZER_CONTENT_ID
 def __post_init__(self):
  object.__setattr__(self,"name",_text(self.name,"channel")); object.__setattr__(self,"analyzer",_text(self.analyzer,"analyzer"))
  if self.name not in CHANNELS or self.status not in {"complete","empty","failed"}: raise ValueError("channel status")
  if self.analyzer!=_approved_analyzer(self.name) or self.analyzer_content_id!=_PINNED_ANALYZER_CONTENT_ID: raise ValueError("approved analyzer")
  _count(self.depth,"depth")
  if self.status=="complete" and not self.depth: raise ValueError("complete depth")
@dataclass(frozen=True)
class Hit:
 candidate_id:str; source_id:str; source_version:str; content_digest:str; section_id:str; span:tuple[int,int]; source_locale:str; source_market:str; access_scope:str; scores:tuple[tuple[str,int,float],...]; source_kind:str="policy"
 def __post_init__(self):
  for n in ("candidate_id","source_id","source_version","content_digest","section_id","source_locale","access_scope"): object.__setattr__(self,n,_text(getattr(self,n),n))
  object.__setattr__(self,"source_market",_market(self.source_market))
  if self.access_scope not in {"public","approved_internal"} or self.source_kind not in {"policy","directory"}: raise ValueError("source scope")
  if type(self.span)is not tuple or len(self.span)!=2 or any(type(x)is not int for x in self.span) or not 0<=self.span[0]<self.span[1]: raise ValueError("span")
  if type(self.scores)is not tuple or any(type(x)is not tuple or len(x)!=3 for x in self.scores) or len({x[0] for x in self.scores})!=len(self.scores): raise ValueError("scores")
  for channel,rank,score in self.scores:
   if channel not in CHANNELS or type(rank)is not int or rank<1: raise ValueError("rank")
   _number(score)
@dataclass(frozen=True)
class Witness:
 reviewer_id:str; judgment_id:str; judgment_digest:str; source_id:str; source_version:str; content_digest:str; section_id:str; span:tuple[int,int]
 def __post_init__(self):
  for n in ("reviewer_id","judgment_id","judgment_digest","source_id","source_version","content_digest","section_id"): object.__setattr__(self,n,_text(getattr(self,n),n))
  if type(self.span)is not tuple or len(self.span)!=2 or any(type(x)is not int for x in self.span) or not 0<=self.span[0]<self.span[1]: raise ValueError("witness span")
@dataclass(frozen=True)
class Capture:
 case_id:str; family:str; provenance:str; split:str; original:str; standalone:str; scope:Scope; corpus_id:str; corpus_version:str; channels:tuple[ChannelConfig,...]; current_order:tuple[str,...]; hits:tuple[Hit,...]; witnesses:tuple[Witness,...]; state:State=State.COMPLETED; reason:str|None=None
 def __post_init__(self):
  for n in ("case_id","family","provenance","split","original","standalone","corpus_id","corpus_version"): object.__setattr__(self,n,_text(getattr(self,n),n))
  if not all(type(x)is tuple for x in (self.channels,self.current_order,self.hits,self.witnesses)):raise ValueError("capture collections")
  if self.provenance not in {"synthetic","real"} or self.split not in {"development","held_out"} or not isinstance(self.scope,Scope) or not isinstance(self.state,State): raise ValueError("capture axis")
  if self.state is not State.COMPLETED:
   if self.channels or self.current_order or self.hits or self.witnesses or self.reason is None: raise ValueError("non-completed shape")
   object.__setattr__(self,"reason",_reason(self.reason)); return
  if self.reason is not None or type(self.channels)is not tuple or tuple(x.name for x in self.channels)!=CHANNELS: raise ValueError("channels")
  if not all(isinstance(x,ChannelConfig) for x in self.channels) or type(self.hits)is not tuple or not all(isinstance(x,Hit) for x in self.hits): raise ValueError("capture members")
  if len({x.candidate_id for x in self.hits})!=len(self.hits) or set(self.current_order)!={x.candidate_id for x in self.hits} or len(self.current_order)!=len(self.hits): raise ValueError("current order")
  if type(self.witnesses)is not tuple or not self.witnesses or not all(isinstance(x,Witness) for x in self.witnesses) or len(set(self.witnesses))!=len(self.witnesses): raise ValueError("witnesses")
  configs={x.name:x for x in self.channels}
  if all(x.status=="failed" for x in self.channels):raise ValueError("all channels failed")
  if not self.hits and any(x.status=="failed" for x in self.channels):raise ValueError("failed channel requires unavailable or rejected state")
  for channel,config in configs.items():
   found=[(rank,score) for hit in self.hits for name,rank,score in hit.scores if name==channel]
   if config.status=="complete" and not found: raise ValueError("complete list")
   if config.status!="complete" and found: raise ValueError("non-complete list")
   if any(rank>config.depth for rank,_ in found) or len({rank for rank,_ in found})!=len(found): raise ValueError("channel ranks")
  expected={x.name for x in self.channels if x.status=="complete"}
  if any({name for name,_,_ in hit.scores}!=expected for hit in self.hits):raise ValueError("channel score union")
  for hit in self.hits:
   if hit.source_kind=="policy" and hit.source_market!=self.scope.policy_market:raise ValueError("policy source market")
   if hit.source_kind=="directory" and (self.scope.directory_country is None or hit.source_market!=self.scope.directory_country):raise ValueError("directory source market")
   if hit.access_scope=="approved_internal" and not self.scope.internal_access_allowed:raise ValueError("internal access")
 @property
 def lineage(self):
  sources=tuple(sorted({(x.source_id,x.source_version,x.content_digest) for x in self.hits}|{(x.source_id,x.source_version,x.content_digest) for x in self.witnesses}))
  return _digest((self.original,self.standalone,self.scope,self.corpus_id,self.corpus_version,sources))
 @property
 def identity(self): return _digest((SCHEMA,self.case_id,self.family,self.provenance,self.split,self.original,self.standalone,self.scope,self.corpus_id,self.corpus_version,self.channels,self.current_order,self.hits,self.witnesses,self.state,self.reason))
@dataclass(frozen=True)
class StrategyParameters:
 top_k:int=3; rrf_k:int=60; weights:tuple[tuple[str,float],...]=(("text",1.0),("vector",1.0))
 def __post_init__(self):
  if type(self.top_k)is not int or self.top_k<1 or type(self.rrf_k)is not int or self.rrf_k!=60: raise ValueError("strategy parameters")
  if type(self.weights)is not tuple or any(type(x)is not tuple or len(x)!=2 for x in self.weights) or tuple(x[0] for x in self.weights)!=CHANNELS: raise ValueError("weights")
  for _,weight in self.weights:
   if type(weight)is not float or not _finite(weight) or weight<=0: raise ValueError("weight")
@dataclass(frozen=True)
class Metric:
 strategy:Strategy; top1:bool; topk:bool; rank:int|None; mrr:float
 def __post_init__(self):
  if not isinstance(self.strategy,Strategy) or type(self.top1)is not bool or type(self.topk)is not bool or type(self.mrr)is not float: raise ValueError("metric")
  if self.rank is None:
   if self.top1 or self.topk or self.mrr!=0.0: raise ValueError("miss metric")
  elif type(self.rank)is not int or self.rank<1 or self.top1!=(self.rank==1) or (self.rank==1 and not self.topk) or self.mrr!=1.0/self.rank: raise ValueError("rank metric")
@dataclass(frozen=True)
class CaseRow:
 case_id:str; state:State; reason:str|None; metrics:tuple[Metric,...]
 def __post_init__(self):
  object.__setattr__(self,"case_id",_text(self.case_id,"case id"))
  if not isinstance(self.state,State) or type(self.metrics)is not tuple or tuple(x.strategy for x in self.metrics)!=tuple(Strategy) or not all(isinstance(x,Metric) for x in self.metrics): raise ValueError("row metrics")
  if self.state is State.COMPLETED:
   if self.reason is not None: raise ValueError("completed reason")
  elif self.reason is None: raise ValueError("outcome reason")
  else:
   object.__setattr__(self,"reason",_reason(self.reason))
   if any(x.rank is not None for x in self.metrics): raise ValueError("non-comparable metric")
@dataclass(frozen=True)
class Axis:
 provenance:str; split:str; cases:tuple[CaseRow,...]; total:int; comparable:int; unavailable:int; rejected:int; denominators:tuple[tuple[Strategy,int|None],...]
 def __post_init__(self):
  if (self.provenance,self.split) not in AXES or type(self.cases)is not tuple or len({x.case_id for x in self.cases})!=len(self.cases) or not all(isinstance(x,CaseRow) for x in self.cases): raise ValueError("axis")
  for n in ("total","comparable","unavailable","rejected"): _count(getattr(self,n),n)
  if self.total!=len(self.cases) or self.total!=self.comparable+self.unavailable+self.rejected: raise ValueError("axis conservation")
  states=[x.state for x in self.cases]
  if (self.comparable,self.unavailable,self.rejected)!=(states.count(State.COMPLETED),states.count(State.UNAVAILABLE),states.count(State.REJECTED)): raise ValueError("axis state counts")
  if type(self.denominators)is not tuple or any(type(x)is not tuple or len(x)!=2 or type(x[1]) not in (int,type(None)) for x in self.denominators) or tuple(x[0] for x in self.denominators)!=tuple(Strategy) or any(x[1]!=(self.comparable if self.comparable else None) for x in self.denominators): raise ValueError("axis denominators")
@dataclass(frozen=True)
class OwnedReport:
 schema:str; registry_version:str; authority_content_id:str; ledger_version:str; ledger_content_id:str; run_id:str; canonical_ids:tuple[str,...]; ordered_case_ids:tuple[str,...]; capture_identities:tuple[str,...]; parameters:StrategyParameters; rows:tuple[CaseRow,...]; axes:tuple[Axis,...]; checksum:str
 def __post_init__(self):
  if self.schema!=SCHEMA or any(not isinstance(x,str) or not x.strip() for x in (self.registry_version,self.authority_content_id,self.ledger_version,self.ledger_content_id,self.run_id,self.checksum)) or any(type(x)is not tuple for x in (self.canonical_ids,self.ordered_case_ids,self.capture_identities,self.rows,self.axes)) or not isinstance(self.parameters,StrategyParameters) or tuple(x.case_id for x in self.rows)!=self.ordered_case_ids or len(set(self.ordered_case_ids))!=len(self.ordered_case_ids): raise ValueError("owned report")
  if tuple((x.provenance,x.split) for x in self.axes)!=AXES or len(self.canonical_ids)!=len(set(self.canonical_ids)) or not set(self.ordered_case_ids).issubset(self.canonical_ids): raise ValueError("axis completeness")
  if globals().get("_PINNED_CANONICAL_IDS") and self.canonical_ids!=_PINNED_CANONICAL_IDS:raise ValueError("pinned canonical ids")
  axis_rows=tuple(row for axis in self.axes for row in axis.cases)
  if len(axis_rows)!=len(self.rows) or {x.case_id for x in axis_rows}!={x.case_id for x in self.rows} or len({x.case_id for x in axis_rows})!=len(axis_rows): raise ValueError("report case conservation")
  if {x.case_id:x for x in axis_rows}!={x.case_id:x for x in self.rows} or len(self.capture_identities)!=len(self.rows) or len(set(self.capture_identities))!=len(self.capture_identities) or any(not isinstance(x,str) or not x.strip() for x in self.capture_identities): raise ValueError("axis correspondence")
  for row in self.rows:
   for metric in row.metrics:
    if metric.topk != (metric.rank is not None and metric.rank<=self.parameters.top_k):raise ValueError("metric parameter binding")
  payload=(self.schema,self.registry_version,self.authority_content_id,self.ledger_version,self.ledger_content_id,self.run_id,self.canonical_ids,self.ordered_case_ids,self.capture_identities,self.parameters,self.rows,self.axes)
  if self.checksum!=_digest(payload): raise ValueError("report checksum")
def _ordered(c,strategy,p):
 if not c.hits:return ()
 if strategy is Strategy.CURRENT:return c.current_order
 weights=dict(p.weights); scale_weight=max(weights.values()); totals={hit.candidate_id:0.0 for hit in c.hits}
 if strategy is Strategy.NORMALIZED:
  for channel in CHANNELS:
   values=[(hit,next((score for name,_,score in hit.scores if name==channel),None)) for hit in c.hits]; present=[score for _,score in values if score is not None]
   if not present:continue
   lo,hi=min(present),max(present); scale=max(abs(lo),abs(hi),1.0)
   for hit,score in values:
    normal=0.0 if score is None or lo==hi else ((score/scale)-(lo/scale))/((hi/scale)-(lo/scale))
    totals[hit.candidate_id]+=(weights[channel]/scale_weight)*normal
 else:
  for hit in c.hits:
   for channel,rank,_ in hit.scores: totals[hit.candidate_id]+=(weights[channel]/scale_weight)/(p.rrf_k+rank)
 return tuple(x.candidate_id for x in sorted(c.hits,key=lambda x:(-totals[x.candidate_id],x.candidate_id)))
def _row(c,p):
 if c.state is not State.COMPLETED:return CaseRow(c.case_id,c.state,c.reason,tuple(Metric(s,False,False,None,0.0) for s in Strategy))
 witnesses={(x.source_id,x.source_version,x.content_digest,x.section_id,x.span) for x in c.witnesses}; metrics=[]
 for strategy in Strategy:
  order=_ordered(c,strategy,p); rank=next((i for i,candidate in enumerate(order,1) if any((hit.source_id,hit.source_version,hit.content_digest,hit.section_id,hit.span) in witnesses for hit in c.hits if hit.candidate_id==candidate)),None)
  metrics.append(Metric(strategy,rank==1,rank is not None and rank<=p.top_k,rank,0.0 if rank is None else 1.0/rank))
 return CaseRow(c.case_id,State.COMPLETED,None,tuple(metrics))
def _axes(captures,rows):
 by_id={row.case_id:row for row in rows}; result=[]
 for provenance,split in AXES:
  chosen=tuple(by_id[x.case_id] for x in captures if (x.provenance,x.split)==(provenance,split)); comparable=sum(x.state is State.COMPLETED for x in chosen); unavailable=sum(x.state is State.UNAVAILABLE for x in chosen); rejected=sum(x.state is State.REJECTED for x in chosen)
  result.append(Axis(provenance,split,chosen,len(chosen),comparable,unavailable,rejected,tuple((s,comparable if comparable else None) for s in Strategy)))
 return tuple(result)
def _admit(case_ids,registry_version,authority_content_id,ledger_version,ledger_content_id):
 if type(case_ids)is not tuple or not case_ids or any(not isinstance(x,str) or not x for x in case_ids):raise ValueError("canonical case ids")
 if registry_version!=_PINNED_AUTHORITY_VERSION or authority_content_id!=_PINNED_AUTHORITY_CONTENT_ID:raise ValueError("pinned authority")
 if ledger_version!=_PINNED_LEDGER_VERSION or ledger_content_id!=_PINNED_LEDGER_CONTENT_ID:raise ValueError("pinned ledger")
 if len(set(case_ids))!=len(case_ids) or any(x not in _PINNED_CANONICAL_IDS for x in case_ids):raise ValueError("unknown or duplicate canonical id")
 captures=tuple(next(x for x in _PINNED_RECORDS if x.case_id==case_id) for case_id in case_ids)
 if any((x.lineage,x.provenance,x.split) not in _PINNED_LEDGER_ASSIGNMENTS for x in captures):raise ValueError("pre-exposure assignment")
 return _PINNED_CANONICAL_IDS,captures
def run_owned(case_ids,run_id,parameters,registry_version,authority_content_id,ledger_version,ledger_content_id):
 """The only producer for a retained V2-06 report."""
 run_id=_text(run_id,"run id")
 if not isinstance(parameters,StrategyParameters):raise ValueError("strategy parameters")
 canonical_ids,captures=_admit(case_ids,registry_version,authority_content_id,ledger_version,ledger_content_id); rows=tuple(_row(c,parameters) for c in captures); axes=_axes(captures,rows); identities=tuple(c.identity for c in captures)
 payload=(SCHEMA,registry_version,authority_content_id,ledger_version,ledger_content_id,run_id,canonical_ids,case_ids,identities,parameters,rows,axes)
 return OwnedReport(SCHEMA,registry_version,authority_content_id,ledger_version,ledger_content_id,run_id,canonical_ids,case_ids,identities,parameters,rows,axes,_digest(payload))
def validate_owned(expected_canonical_ids,expected_order,run_id,parameters,registry_version,authority_content_id,ledger_version,ledger_content_id,report):
 """The only consumer boundary; expectations are independent of the report."""
 if not isinstance(report,OwnedReport) or type(expected_canonical_ids)is not tuple or type(expected_order)is not tuple:raise ValueError("owned report expectations")
 fresh=run_owned(expected_order,run_id,parameters,registry_version,authority_content_id,ledger_version,ledger_content_id)
 if expected_canonical_ids!=fresh.canonical_ids or report!=fresh:raise ValueError("stale or substituted owned report")
 return report

# Bound once by value. Public fixture suppliers are inspection-only and cannot redirect routes.
_fixture=__import__(__package__+".ranking_fixture",fromlist=("authority",))
_reviewed=_fixture.authority()
_PINNED_AUTHORITY_VERSION=_reviewed.version
_PINNED_RECORDS=tuple(_reviewed.records)
_PINNED_CANONICAL_IDS=tuple(x.case_id for x in _PINNED_RECORDS)
AUTHORITY_CONTENT_ID=_digest((_PINNED_AUTHORITY_VERSION,tuple(x.identity for x in _PINNED_RECORDS)))
_PINNED_AUTHORITY_CONTENT_ID=AUTHORITY_CONTENT_ID
_ledger=__import__(__package__+".ranking_ledger",fromlist=("assignments","LEDGER_VERSION","LEDGER_CONTENT_ID"))
_PINNED_LEDGER_ASSIGNMENTS=tuple(_ledger.assignments())
_PINNED_LEDGER_VERSION=_ledger.LEDGER_VERSION
_PINNED_LEDGER_CONTENT_ID=_ledger.LEDGER_CONTENT_ID
