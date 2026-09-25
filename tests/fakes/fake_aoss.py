"""Fake OpenSearch Serverless VECTORSEARCH (Classic) client for offline checks.

Rules (docs.aws.amazon.com serverless-genref / serverless-clients / serverless-vector-search):
- index/create with a client _id -> per-item 400 (custom IDs unsupported on vector collections)
- update (bulk or _update/<id>) -> per-item 400 (search collection types only)
- delete by _id -> supported
- _delete_by_query, _update_by_query, _refresh -> not in the supported API table -> 404
- new docs become searchable only after a refresh tick (60 s on Classic vector)
"""
from __future__ import annotations

import json
import uuid

from opensearchpy.exceptions import NotFoundError, RequestError


class _Indices:
    def __init__(self, outer):
        self.o = outer

    def exists(self, index):
        return index in self.o.indexes

    def create(self, index, body=None):
        self.o.indexes.add(index)
        return {"acknowledged": True}

    def refresh(self, index=None, **kw):
        raise NotFoundError(404, "no handler found for uri [/_refresh]", {})


class FakeAOSSVector:
    def __init__(self):
        self.indexes = {"askvera-policy-sections"}
        self.docs: dict[str, dict] = {}
        self.visible: set[str] = set()
        self.indices = _Indices(self)
        from types import SimpleNamespace
        from opensearchpy.serializer import JSONSerializer
        self.transport = SimpleNamespace(serializer=JSONSerializer())

    def tick(self):
        self.visible = set(self.docs)

    def bulk(self, body, index=None, **params):
        if isinstance(body, (bytes, str)):
            text = body.decode() if isinstance(body, bytes) else body
            lines = [line for line in text.splitlines() if line.strip()]
        else:
            lines = [line.decode() if isinstance(line, bytes) else (line if isinstance(line, str) else json.dumps(line)) for line in body]
        items, errors = [], False
        it = iter(lines)
        for line in it:
            meta = json.loads(line)
            op, m = next(iter(meta.items()))
            src = json.loads(next(it)) if op in ("index", "create", "update") else None
            if op in ("index", "create") and "_id" in m:
                items.append({op: {"_index": m.get("_index"), "_id": m["_id"], "status": 400, "error": {"type": "illegal_argument_exception", "reason": "Document ID is not supported in create/index operation request"}}})
                errors = True
                continue
            if op == "update":
                items.append({op: {"_index": m.get("_index"), "_id": m.get("_id"), "status": 400, "error": {"type": "illegal_argument_exception", "reason": "update by id is supported only for SEARCH collections"}}})
                errors = True
                continue
            if op in ("index", "create"):
                _id = uuid.uuid4().hex[:20]
                self.docs[_id] = src
                items.append({op: {"_index": m.get("_index"), "_id": _id, "status": 201, "result": "created"}})
            elif op == "delete":
                found = self.docs.pop(m["_id"], None) is not None
                self.visible.discard(m["_id"])
                items.append({op: {"_index": m.get("_index"), "_id": m["_id"], "status": 200 if found else 404, "result": "deleted" if found else "not_found"}})
        return {"took": 1, "errors": errors, "items": items}

    def delete_by_query(self, *a, **k):
        raise NotFoundError(404, "no handler found for uri [/_delete_by_query]", {})

    def update_by_query(self, *a, **k):
        raise NotFoundError(404, "no handler found for uri [/_update_by_query]", {})

    def update(self, *a, **k):
        raise RequestError(400, "illegal_argument_exception", {})

    def index(self, index, body, id=None, **k):
        if id is not None:
            raise RequestError(400, "Document ID is not supported in create/index operation request", {})
        _id = uuid.uuid4().hex[:20]
        self.docs[_id] = body
        return {"_id": _id, "result": "created"}

    def delete(self, index, id, **k):
        if id not in self.docs:
            raise NotFoundError(404, "not_found", {})
        self.docs.pop(id)
        self.visible.discard(id)
        return {"result": "deleted"}

    def _match(self, src, q):
        if not q:
            return True
        if "bool" in q:
            b = q["bool"]
            if not all(self._match(src, f) for f in b.get("filter", [])):
                return False
            if b.get("should") and b.get("minimum_should_match", 0):
                return any(self._match(src, s) for s in b["should"])
            return True
        if "term" in q:
            (k, v), = q["term"].items()
            v = v["value"] if isinstance(v, dict) else v
            return src.get(k.removesuffix(".keyword")) == v
        if "terms" in q:
            (k, v), = q["terms"].items()
            return src.get(k.removesuffix(".keyword")) in v
        return True

    def count(self, index, body=None, **k):
        q = (body or {}).get("query")
        return {"count": sum(1 for i in self.visible if self._match(self.docs[i], q))}

    def search(self, index, body=None, **k):
        q = (body or {}).get("query")
        size = (body or {}).get("size", 10)
        hits = [{"_id": i, "_source": self.docs[i], "sort": [i]} for i in sorted(self.visible) if self._match(self.docs[i], q)]
        sa = (body or {}).get("search_after")
        if sa:
            hits = [h for h in hits if h["_id"] > sa[0]]
        return {"hits": {"hits": hits[:size]}}
