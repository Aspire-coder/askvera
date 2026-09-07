"""Read-only OpenSearch metadata check against an exported publication registry."""
import argparse
import collections
import datetime
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit, urlunsplit

import boto3
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection


def main():
    folder = Path(__file__).resolve().parents[1] / "docs/audits/2026-09-05"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=folder / 'active-source-metadata.json')
    parser.add_argument('--output', type=Path, default=folder / 'active-index-metadata-v2.json')
    parser.add_argument('--all-markets', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Refusing to overwrite an existing audit')
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    session = boto3.Session(profile_name="askvera-review", region_name="us-east-1")
    ssm = session.client("ssm")
    names = ["/askverachat/prod/" + key for key in ("OPENSEARCH_ENDPOINT", "OPENSEARCH_INDEX")]
    parameters = ssm.get_parameters(Names=names, WithDecryption=False)
    if parameters.get("InvalidParameters") or any(p["Type"] != "String" for p in parameters["Parameters"]):
        raise RuntimeError("Expected nonsecret index configuration unavailable")
    config = {p["Name"].rsplit("/", 1)[-1]: p["Value"] for p in parameters["Parameters"]}
    endpoint = urlsplit(config["OPENSEARCH_ENDPOINT"])
    if endpoint.scheme != "https" or not endpoint.hostname.endswith(".us-east-1.aoss.amazonaws.com"):
        raise RuntimeError("Unexpected index endpoint")
    client = OpenSearch(hosts=[{"host": endpoint.hostname, "port": 443}],
                        http_auth=AWSV4SignerAuth(session.get_credentials(), "us-east-1", "aoss"),
                        use_ssl=True, verify_certs=True, connection_class=RequestsHttpConnection,
                        timeout=20, max_retries=1)
    fields = ["ingestion_id", "logical_document_id", "source_file", "source_uri", "content_hash",
              "country", "language", "access_scope", "document_type", "document_version",
              "status", "section_id", "start_page", "end_page", "effective_date", "expiry_date", "metadata"]
    results = []
    try:
        for generation in snapshot["active_generations"]:
            if not args.all_markets and (generation["country"] not in ("US", "UK", "GB", "GLOBAL") or generation["language"] != "en"):
                continue
            identifier = generation["active_ingestion_id"]
            query = {"size": 2000, "track_total_hits": True, "_source": fields,
                     "query": {"bool": {"should": [{"term": {"ingestion_id": identifier}},
                                                     {"term": {"ingestion_id.keyword": identifier}}],
                                        "minimum_should_match": 1}}}
            response = client.search(index=config["OPENSEARCH_INDEX"], body=query)
            if response.get("timed_out") or response.get("_shards", {}).get("failed", 0):
                raise RuntimeError("Incomplete index response")
            hits = response["hits"]
            total = hits["total"]["value"]
            rows = []
            for hit in hits["hits"]:
                row = dict(hit["_source"], index_id=hit["_id"])
                if row.get("source_uri"):
                    uri = urlsplit(row["source_uri"])
                    row["source_uri"] = urlunsplit((uri.scheme, uri.netloc, uri.path, "", ""))
                rows.append(row)
            summary = {field: dict(collections.Counter(str(row.get(field, "")) for row in rows))
                       for field in ("country", "language", "access_scope", "status", "logical_document_id",
                                     "content_hash", "source_file", "source_uri", "document_version")}
            result = {"generation": generation, "total": total,
                      "complete": hits["total"].get("relation") == "eq" and total == len(rows),
                      "summary": summary, "rows": rows}
            results.append(result)
            if total == 0:
                filename_query = {"size": 2000, "track_total_hits": True, "_source": fields,
                                  "query": {"bool": {"should": [
                                      {"term": {"source_file": generation["source_file"]}},
                                      {"term": {"source_file.keyword": generation["source_file"]}},
                                      {"match_phrase": {"source_file": generation["source_file"]}}],
                                      "minimum_should_match": 1}}}
                alternative = client.search(index=config["OPENSEARCH_INDEX"], body=filename_query)
                if alternative.get("timed_out") or alternative.get("_shards", {}).get("failed", 0):
                    raise RuntimeError("Incomplete filename lookup")
                result["filename_lookup"] = alternative["hits"]
            print(json.dumps({"source": generation["source_file"], "count": total,
                              "complete": result["complete"],
                              "filename_lookup_total": result.get("filename_lookup", {}).get("total")}), flush=True)
    finally:
        client.close()
    report = {"captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "registry_captured_at": snapshot["captured_at"], "index": config["OPENSEARCH_INDEX"],
              "endpoint": config["OPENSEARCH_ENDPOINT"], "results": results,
              "limits": ["Metadata only; no source bytes verified", "All registry markets/languages" if args.all_markets else "Selected US, UK/GB and GLOBAL English generations only",
                         "Registry and index reads are not an atomic combined snapshot"]}
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
