"""Offline V2-04 canonical composition gate; provider data is untrusted."""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Callable, Iterable
from .contracts import EvidenceFact, EvidenceFirstResult, ResultStatus, V2Request, _enum, _required, _tuple_of
from .scope import ScopeDecision, resolve_scope
from .standalone import StandaloneRequest, resolve_standalone_scope
_evidence = __import__(__package__ + ".evidence", fromlist=("assess_coverage",))

class FailureCode(str, Enum):
    HANDOFF_INVALID="handoff_invalid"; COVERAGE_UNCERTAIN="coverage_uncertain"; CLAIM_UNSUPPORTED="claim_unsupported"; CITATION_MISMATCH="citation_mismatch"; COMPOSER_FAULT="composer_fault"; UNSAFE_AFFIRMATIVE="unsafe_affirmative"; UNJUSTIFIED_REFUSAL="unjustified_refusal"; REFUSED_SAFETY="refused_safety"; CORRECTION_EXHAUSTED="correction_exhausted"
class PublicStatus(str, Enum): READY="ready"; SAFE_PARTIAL="safe_partial"; CLARIFICATION="clarification"; BLOCKED="blocked"; REFUSED="refused"
@dataclass(frozen=True)
class CompositionInput:
    request_id:str; message:str; scope:ScopeDecision; facts:tuple[EvidenceFact,...]; attempt:int; prior_failures:tuple[FailureCode,...]=()
    def __post_init__(self):
        object.__setattr__(self,"request_id",_required(self.request_id,"request_id")); object.__setattr__(self,"message",_required(self.message,"message"))
        if not isinstance(self.scope,ScopeDecision) or isinstance(self.attempt,bool) or self.attempt not in (0,1): raise ValueError("invalid composition input")
        object.__setattr__(self,"facts",_tuple_of(self.facts,EvidenceFact,"facts")); object.__setattr__(self,"prior_failures",_tuple_of(self.prior_failures,FailureCode,"prior failures"))
@dataclass(frozen=True)
class CandidateCitation:
    fact_index:int; evidence:object
    def __post_init__(self):
        if isinstance(self.fact_index,bool) or not isinstance(self.fact_index,int) or self.fact_index<0: raise ValueError("citation index")
@dataclass(frozen=True)
class ComposerOutput:
    answer:str; claim_indices:tuple[int,...]=(); citations:tuple[CandidateCitation,...]=(); refusal:bool=False
    def __post_init__(self):
        object.__setattr__(self,"answer",_required(self.answer,"composer answer")); object.__setattr__(self,"claim_indices",_tuple_of(self.claim_indices,int,"claim indices")); object.__setattr__(self,"citations",_tuple_of(self.citations,CandidateCitation,"citations"))
        if any(type(index) is not int for index in self.claim_indices): raise ValueError("claim indices must be integers")
        if not isinstance(self.refusal,bool): raise ValueError("refusal must be bool")
@dataclass(frozen=True)
class OrchestrationResult:
    status:PublicStatus; answer:str; citations:tuple[EvidenceFact,...]; failure_codes:tuple[FailureCode,...]; invocation_count:int; final:EvidenceFirstResult
    def __post_init__(self):
        object.__setattr__(self,"status",_enum(self.status,PublicStatus,"status")); object.__setattr__(self,"answer",_required(self.answer,"answer")); object.__setattr__(self,"citations",_tuple_of(self.citations,EvidenceFact,"citations")); object.__setattr__(self,"failure_codes",_tuple_of(self.failure_codes,FailureCode,"failure codes"))
        if isinstance(self.invocation_count,bool) or self.invocation_count not in (0,1,2): raise ValueError("invocation count")
Composer=Callable[[CompositionInput],ComposerOutput]; DiagnosticSink=Callable[[tuple[FailureCode,...]],None]
_NEG=re.compile(r"\b(?:income|earnings?)\s+(?:is\s+)?not\s+(?:guaranteed|assured)|\b(?:learning|treat\s+customers)\b")
_AFF=re.compile(r"\b(?:you\s+will\s+)?make\s+\$?\d+(?:\s+every\s+day)?\b|\bincome\s+is\s+guaranteed\b|\beliminates\s+diabetes\b")
_RISK=re.compile(r"\b(?:income|earnings?|diabetes|medical)\b")
_REFUSE_REQUEST=re.compile(r"\b(?:will|can)\s+(?:i|you)\s+make\s+\$?\d+|\bguaranteed\s+(?:income|earnings)\b|\b(?:cure|eliminate)\s+diabetes\b")
def _normal(text:str)->str: return unicodedata.normalize("NFKC",text).casefold()
def _refusal_words(text:str)->str:
    return " ".join("".join(" " if unicodedata.category(c)=="Cf" or unicodedata.category(c)=="Pd" or c in "()[]{}:/" else c for c in _normal(text)).split())
def _safety(text:str)->bool:
    value=_normal(text); folded=value
    if any(any("LATIN" in unicodedata.name(c,"") for c in token) and any("CYRILLIC" in unicodedata.name(c,"") for c in token) for token in re.findall(r"[A-Za-z\u0400-\u04ff]+",value)): return True
    if any(unicodedata.category(c)=="Cf" for c in value) and _RISK.search("".join(c for c in folded if unicodedata.category(c)!="Cf")): return True
    if _AFF.search(folded): return True
    return any(_RISK.search(clause) and not _NEG.search(clause) for clause in re.split(r"[;,:/.!?\r\n]+",folded))

class EvidenceFirstOrchestrator:
    def __init__(self,composer:Composer,diagnostic_sink:DiagnosticSink|None=None):
        if not callable(composer): raise ValueError("composer must be callable")
        self._composer=composer; self._sink=diagnostic_sink or (lambda _codes:None)
    def run(self,actual:V2Request,standalone:StandaloneRequest,branches:Iterable[Any],catalog:Any,facts:Iterable[Any],coverage:Any)->OrchestrationResult:
        try:
            scope=resolve_standalone_scope(standalone); canonical=self._canonical(actual,standalone)
            if scope != resolve_scope(canonical,standalone.intent): raise ValueError("scope mismatch")
            expected=(_evidence.build_coverage_branch(canonical,scope,catalog),); supplied=_tuple_of(branches,_evidence.CoverageBranch,"branches")
            if supplied != expected: raise ValueError("branches must exactly match accepted handoff scope")
            submitted=_tuple_of(facts,_evidence.ValidatedFact,"facts"); fresh=_evidence.validate_facts(tuple(item.candidate for item in submitted),catalog,scope)
            ordered=tuple(sorted(fresh,key=lambda item:(item.fact.evidence.source_id,item.fact.evidence.section_id,item.candidate.source_reference.start,item.candidate.source_reference.end,item.fact_identity)))
            if submitted != ordered or len({item.fact_identity for item in ordered})!=len(ordered): raise ValueError("facts must be fresh, unique, and canonical order")
            aspects=_evidence._aspects(canonical,catalog,scope); groups=[]
            for aspect in aspects:
                rules=_evidence._manifest_rules(catalog,aspect)
                singles={}; alternatives={}
                for section in _evidence._governing_sections(catalog,scope,aspect):
                    for annotation,group in _evidence._requirements(section,aspect,rules):
                        key=(section.source_id,section.section_id,annotation.aspect,annotation.start,annotation.end,annotation.value)
                        (alternatives.setdefault(group,[] ) if group else singles.setdefault(key,[])).append(key)
                groups.extend((key,) for key in singles)
                groups.extend(tuple(keys) for _name,keys in sorted(alternatives.items()))
            assessment=_evidence.assess_coverage(canonical,expected,catalog,ordered)
        except (ValueError,TypeError): return self._public(PublicStatus.CLARIFICATION,"Please clarify the request.",(),(FailureCode.HANDOFF_INVALID,),0,"handoff unavailable")
        if assessment.status is not _evidence.CoverageStatus.COMPLETE:
            return self._public(PublicStatus.SAFE_PARTIAL,"I need the governing conditions to answer safely.",(),(FailureCode.COVERAGE_UNCERTAIN,),0,scope.reason)
        selected=[]
        for group in groups:
            witness=next((item for item in ordered if any((item.fact.evidence.source_id,item.fact.evidence.section_id,s.aspect,s.start,s.end,s.value) in group for s in item.candidate.supports)),None)
            if witness is None: return self._public(PublicStatus.SAFE_PARTIAL,"I need the governing conditions to answer safely.",(),(FailureCode.COVERAGE_UNCERTAIN,),0,scope.reason)
            if witness not in selected: selected.append(witness)
        return self._compose(canonical,scope,tuple(item.fact for item in selected))
    def _canonical(self,actual,standalone):
        values=((actual.request_id,standalone.request_id),(actual.message,standalone.original_message),(actual.user_market,standalone.user_market),(actual.role,standalone.role),(actual.language,standalone.language),(actual.effective_version,standalone.effective_version))
        if not isinstance(actual,V2Request) or any(left!=right for left,right in values) or standalone.standalone_message!=actual.message: raise ValueError("handoff does not bind request fields")
        return replace(actual,turns=(),requested_directory_market=standalone.requested_directory_market)
    def _compose(self,request,scope,facts):
        failures:tuple[FailureCode,...]=()
        for attempt in (0,1):
            try: output=self._composer(CompositionInput(request.request_id,request.message,scope,facts,attempt,failures))
            except Exception: failures=(FailureCode.COMPOSER_FAULT,)
            else:
                if not isinstance(output,ComposerOutput): failures=(FailureCode.COMPOSER_FAULT,)
                elif output.refusal:
                    message=_refusal_words(request.message)
                    positives=tuple(_REFUSE_REQUEST.finditer(message))
                    allowed=any(not re.search(r"\b(?:not|no|never)\s+$",message[max(0,item.start()-48):item.start()]) for item in positives)
                    if positives and allowed and not output.claim_indices and not output.citations:
                        return self._public(PublicStatus.REFUSED,"I cannot provide affirmative income or medical claims.",(),(FailureCode.REFUSED_SAFETY,),attempt+1,scope.reason)
                    failures=(FailureCode.UNJUSTIFIED_REFUSAL,)
                else: failures=self._validate(output,facts)
            if not failures: return self._public(PublicStatus.READY,"\n".join(item.text for item in facts),facts,(),attempt+1,scope.reason)
            self._sink(failures)
        return self._public(PublicStatus.BLOCKED,"I cannot provide that answer safely.",(),failures+(FailureCode.CORRECTION_EXHAUSTED,),2,scope.reason)
    def _validate(self,output,facts):
        if _safety(output.answer): return (FailureCode.UNSAFE_AFFIRMATIVE,)
        expected=tuple(range(len(facts)))
        if output.claim_indices!=expected: return (FailureCode.CLAIM_UNSUPPORTED,)
        if tuple(c.fact_index for c in output.citations)!=expected or any(c.evidence != facts[c.fact_index].evidence for c in output.citations): return (FailureCode.CITATION_MISMATCH,)
        if output.answer!="\n".join(f.text for f in facts): return (FailureCode.CLAIM_UNSUPPORTED,)
        return ()
    @staticmethod
    def _public(status,answer,citations,codes,count,reason):
        final_status=ResultStatus.READY if status is PublicStatus.READY else (ResultStatus.SAFE_PARTIAL if status is PublicStatus.SAFE_PARTIAL else (ResultStatus.CLARIFICATION if status is PublicStatus.CLARIFICATION else ResultStatus.BLOCKED))
        return OrchestrationResult(status,answer,citations,codes,count,EvidenceFirstResult(final_status,reason,citations if final_status is ResultStatus.READY else (),answer,tuple(code.value for code in codes)))
