"""Hash three approved S3 source objects without modifying or publishing data."""
import datetime
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

import boto3


def main():
    folder = Path(__file__).resolve().parents[1] / 'docs/audits/2026-09-05'
    registry = json.loads((folder / 'active-source-metadata.json').read_text(encoding='utf-8'))
    index = json.loads((folder / 'active-index-metadata-v2.json').read_text(encoding='utf-8'))
    retirement = json.loads((folder / 'office-directory-retirement-after.json').read_text(encoding='utf-8'))
    global_ids = {r['active_ingestion_id'] for r in retirement['verified_global_publications']}
    s3 = boto3.Session(profile_name='askvera-review', region_name='us-east-1').client('s3')
    results = []
    for group in index['results']:
        generation = group['generation']
        if generation['access_scope'] == 'global' and generation['active_ingestion_id'] not in global_ids:
            continue
        matches = [d for d in registry['documents'] if d['filename'] == generation['source_file']
                   and d['language'] == generation['language'] and d['access_scope'] == generation['access_scope']]
        uris = list(group['summary']['source_uri'])
        if len(matches) != 1 or len(uris) != 1:
            raise RuntimeError('Ambiguous source identity')
        uri = urlsplit(uris[0])
        if uri.scheme != 's3' or uri.netloc != 'askverachat-prod-kb' or not uri.path.startswith('/approved/'):
            raise RuntimeError('Unexpected source location')
        head = s3.head_object(Bucket=uri.netloc, Key=uri.path.lstrip('/'))
        request = dict(Bucket=uri.netloc, Key=uri.path.lstrip('/'), IfMatch=head['ETag'])
        if head.get('VersionId'):
            request['VersionId'] = head['VersionId']
        result = s3.get_object(**request)
        digest = hashlib.sha256()
        length = 0
        try:
            for chunk in result['Body'].iter_chunks(chunk_size=1024 * 1024):
                length += len(chunk)
                digest.update(chunk)
        finally:
            result['Body'].close()
        if length != head['ContentLength']:
            raise RuntimeError('Incomplete source read')
        row = dict(filename=generation['source_file'], source_uri=uris[0],
                   active_ingestion_id=generation['active_ingestion_id'], bytes=length,
                   etag=head['ETag'], s3_version_id=head.get('VersionId'),
                   last_modified=head['LastModified'].isoformat(), sha256=digest.hexdigest(),
                   registry_sha256=matches[0]['content_hash'],
                   registry_hash_matches=digest.hexdigest() == matches[0]['content_hash'])
        results.append(row)
        print(json.dumps(row), flush=True)
    report = {'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'results': results,
              'limits': ['Does not prove index text matches PDF contents',
                         'Registry snapshot plus verified retirement; other concurrent changes not excluded']}
    with (folder / 'comparison-source-file-hashes.json').open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
