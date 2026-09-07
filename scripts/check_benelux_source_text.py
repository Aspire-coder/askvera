"""Read the two split S3 PDFs and locate reviewed clauses, with version checks."""
import io
import json
from pathlib import Path
from urllib.parse import urlsplit

import boto3
from pypdf import PdfReader


def main():
    audit = Path(__file__).resolve().parents[1] / 'docs/audits/2026-09-05'
    hashes = json.loads((audit / 'market-policy-source-hashes.json').read_text(encoding='utf-8'))
    client = boto3.Session(profile_name='askvera-review', region_name='us-east-1').client('s3')
    results = []
    for row in hashes['results']:
        if row['market'] not in ('BE', 'NL'):
            continue
        uri = urlsplit(row['source_uri'])
        request = dict(Bucket=uri.netloc, Key=uri.path.lstrip('/'), IfMatch=row['etag'])
        if row['version_id']:
            request['VersionId'] = row['version_id']
        stream = client.get_object(**request)['Body']
        try:
            pdf = PdfReader(io.BytesIO(stream.read()))
        finally:
            stream.close()
        selected = []
        for number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ''
            if any(term in text for term in ('13.01', '4.03', '21.03', '21.05')):
                selected.append(dict(pdf_page=number, text=text))
        results.append(dict(market=row['market'], source_uri=row['source_uri'], pages=len(pdf.pages), selected_pages=selected))
    with (audit / 'market-policy-benelux-source-text.json').open('x', encoding='utf-8') as stream:
        json.dump(results, stream, ensure_ascii=False, indent=2)
    for row in results:
        print(row['market'], 'pages', row['pages'])
        for page in row['selected_pages']:
            if '13.01' in page['text'] or '4.03' in page['text']:
                print(page['pdf_page'], page['text'])


if __name__ == '__main__':
    main()
