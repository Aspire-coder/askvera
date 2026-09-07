"""Read-only hashes of the nine indexed source objects and supplied originals."""
import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import boto3
from botocore.config import Config


def main():
    audit = Path(__file__).resolve().parents[1] / 'docs/audits/2026-09-05'
    baseline = json.loads((audit / 'market-policy-active-index-metadata.json').read_text(encoding='utf-8'))
    names = {('BE', 'en'): 'Belgium', ('NL', 'en'): 'Netherlands', ('CA', 'en'): 'Canada',
             ('DE', 'de'): 'Germany', ('IT', 'it'): 'Italy', ('SE', 'en'): 'Sweden',
             ('UK', 'en'): 'U.K.', ('US', 'en'): 'U.S.', ('GLOBAL', 'en'): 'GLOBAL'}
    session = boto3.Session(profile_name='askvera-review', region_name='us-east-1')
    client = session.client('s3', config=Config(connect_timeout=5, read_timeout=30,
                                             retries={'total_max_attempts': 2, 'mode': 'standard'}))
    output = audit / 'market-policy-source-hashes.json'
    if output.exists():
        raise FileExistsError(output)
    rows = []
    for group in baseline['results']:
        g = group['generation']
        name = names.get((g['country'], g['language']))
        if not name:
            continue
        uris = list(group['summary']['source_uri'])
        if len(uris) != 1:
            raise ValueError('Ambiguous source URI')
        uri = urlsplit(uris[0])
        if uri.scheme != 's3' or uri.netloc != 'askverachat-prod-kb' or not uri.path.startswith('/approved/'):
            raise ValueError('Unexpected source location')
        request = dict(Bucket=uri.netloc, Key=uri.path.lstrip('/'))
        head = client.head_object(**request)
        request['IfMatch'] = head['ETag']
        if head.get('VersionId'):
            request['VersionId'] = head['VersionId']
        digest, size = hashlib.sha256(), 0
        stream = client.get_object(**request)['Body']
        try:
            for chunk in stream.iter_chunks(chunk_size=1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        finally:
            stream.close()
        if size != head['ContentLength']:
            raise ValueError('Incomplete object read')
        local = (Path('C:/Users/KRISH/Downloads/International_Sponsoring_Directory (1).pdf') if name == 'GLOBAL'
                 else Path(f'C:/Users/KRISH/AppData/Local/Temp/Forever Living Products {name} Company Policy (1).pdf'))
        local_hash = hashlib.sha256(local.read_bytes()).hexdigest()
        row = dict(market=g['country'], language=g['language'], source_uri=uris[0],
                   ingestion_id=g['active_ingestion_id'], s3_sha256=digest.hexdigest(),
                   supplied_path=str(local), supplied_sha256=local_hash,
                   byte_identical=local_hash == digest.hexdigest(), etag=head['ETag'],
                   version_id=head.get('VersionId'), bytes=size)
        rows.append(row)
        print(f"{g['country']}: byte_identical={row['byte_identical']}", flush=True)
    if len(rows) != 9:
        raise ValueError('Expected exactly nine source objects')
    with output.open('x', encoding='utf-8') as stream:
        json.dump(dict(captured_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), results=rows,
                       limits=['Different bytes do not establish different policy wording; split PDFs require clause comparison.',
                               'Source object hashes do not prove index text faithfully represents each PDF.']), stream, indent=2)


if __name__ == '__main__':
    main()
