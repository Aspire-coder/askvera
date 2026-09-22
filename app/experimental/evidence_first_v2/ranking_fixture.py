"""Application-owned immutable synthetic V2-06 authority manifest."""
from __future__ import annotations
from dataclasses import dataclass
_ranking=__import__(__package__+".ranking",fromlist=("Capture","ChannelConfig","Hit","Scope","State","Witness"))
Capture,ChannelConfig,Hit,Scope,State,Witness=(_ranking.Capture,_ranking.ChannelConfig,_ranking.Hit,_ranking.Scope,_ranking.State,_ranking.Witness)
@dataclass(frozen=True)
class Authority:
 version:str; records:tuple[Capture,...]
 def __post_init__(self):
  if not isinstance(self.version,str) or not self.version.strip() or type(self.records)is not tuple or not self.records or not all(isinstance(x,Capture) for x in self.records) or len({x.case_id for x in self.records})!=len(self.records):raise ValueError("authority records")
 @property
 def canonical_ids(self):return tuple(x.case_id for x in self.records)
 def resolve(self,case_id):
  return next((x for x in self.records if x.case_id==case_id),None)
CFG=(ChannelConfig("text",10,"complete","unicode-word-v1"),ChannelConfig("vector",10,"complete","embedding-offline-v1"))
W=Witness("reviewer-structural","judgment-structural","digest-judgment-1","source","v1","digest-z","gov",(0,8))
Z=Hit("z","source","v1","digest-z","gov",(0,8),"en-US","US","public",(("text",1,10.0),("vector",2,1.0)))
A=Hit("a","source","v1","digest-a","near",(0,8),"en-US","US","public",(("text",2,1.0),("vector",1,10.0)))
CURRENT_WINS=Capture("current-wins","family-a","synthetic","development","original ranking question","standalone ranking question",Scope("US","KE","FBO","en-US"),"corpus","v1",CFG,("z","a"),(Z,A),(W,))
MISS=Capture("miss","family-a","synthetic","development","original miss question","standalone miss question",Scope("US",None,"FBO","en-US"),"corpus","v1",CFG,("a",),(A,),(Witness("reviewer-structural","judgment-miss","digest-judgment-2","source","v1","missing","gov",(0,8)),))
EMPTY=Capture("empty","family-empty","synthetic","development","original empty question","standalone empty question",Scope("US",None,"FBO","en-US"),"corpus","v1",(ChannelConfig("text",10,"empty","unicode-word-v1"),ChannelConfig("vector",10,"empty","embedding-offline-v1")),(),(),(Witness("reviewer-structural","judgment-empty","digest-judgment-3","source","v1","missing-empty","gov",(0,8)),))
UNAVAILABLE=Capture("real-unavailable","real","real","development","original unavailable","standalone unavailable",Scope("US",None,"FBO","en-US"),"none","none",(),(),(),(),State.UNAVAILABLE,"evidence_unavailable")
REJECTED=Capture("reviewed-rejected","family-rejected","synthetic","held_out","original rejected","standalone rejected",Scope("US",None,"FBO","en-US"),"none","none",(),(),(),(),State.REJECTED,"review_rejected")
_RECORDS=(CURRENT_WINS,MISS,EMPTY,UNAVAILABLE,REJECTED)
_AUTHORITY=Authority("v2-06-owned-2",_RECORDS)
def authority():return _AUTHORITY
CANONICAL_IDS=_AUTHORITY.canonical_ids
ALL=_AUTHORITY.records
