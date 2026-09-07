"""Isolated full-chat selector hook. Never imported by the application runtime."""
from dataclasses import asdict

from app.retrieval.governing_rules import prioritize_activity_rule
from app.retrieval.structural_selection import document_sources, select_bound_documents
from scripts.selector_binding_adapter import alias_registry, source_alias, structural_system_prompt, STRUCTURAL_SCHEMA
from scripts.run_selector_fixed_comparison import parse_output


def prepare(provider, rows, question, country, language, active_ids, limit):
    from app.retrieval.opensearch_sections import _selector_candidate_text, _selector_candidates

    candidates = _selector_candidates(rows, limit)
    scores = {id(row): score for row, score in candidates}
    ordered = prioritize_activity_rule(question, [row for row, _ in candidates], language)
    pairs = [(row, scores[id(row)]) for row in ordered]
    documents = [provider._document_from_row(row, score) for row, score in pairs]
    sources = document_sources(documents, country=country, active_ingestion_ids=active_ids,
                               allow_global_sponsoring=True)
    alias_registry(sources)
    blocks = []
    for index, ((row, score), source) in enumerate(zip(pairs, sources), 1):
        block = _selector_candidate_text(row, score, index).split('\n', 1)[1]
        blocks.append(f'Source ID: {source_alias(source)}\n{block}')
    user = (f'User question:\n{question}\n\nCandidate sections:\n' + '\n\n'.join(blocks)
            + f'\n\nSelect up to 5 sources. Return JSON exactly like this: {STRUCTURAL_SCHEMA}.')
    request = {'system': [{'text': structural_system_prompt()}],
               'messages': [{'role': 'user', 'content': [{'text': user}]}]}
    return request, pairs, documents, sources


def resolve(payload, pairs, documents, sources, *, question, country, language, active_ids):
    aliases = alias_registry(sources)
    if not isinstance(payload, dict) or not isinstance(payload.get('support'), list):
        raise ValueError('Invalid support-only response')
    support = []
    for item in payload['support']:
        if not isinstance(item, dict) or set(item) != {'source_id', 'quote'}:
            raise ValueError('Invalid support item')
        if not isinstance(item['source_id'], str) or item['source_id'] not in aliases:
            raise ValueError('Unknown source alias')
        support.append({**item, 'source_id': aliases[item['source_id']]})
    selection = select_bound_documents({**payload, 'support': support}, documents, question=question,
                                       country=country, language=language, active_ingestion_ids=active_ids,
                                       allow_global_sponsoring=True)
    lookup = {document.id: pair for document, pair in zip(documents, pairs)}
    # Preserve existing row scores/signals. Do not promote evidence-set confidence
    # to top-passage confidence or mark strong_local_match. No unselected tail.
    return [lookup[document.id] for document in selection.documents], asdict(selection.decision)


def select(provider, rows, question, country, language, active_ids, limit, client, model, records):
    record = {'question': question, 'country': country, 'language': language,
              'confidence_policy': 'existing lexical calculation; set confidence diagnostic only'}
    records.append(record)
    if not rows:
        record['empty_candidates'] = True
        return []
    try:
        request, pairs, documents, sources = prepare(provider, rows, question, country, language, active_ids, limit)
        record.update(request=request, sources=[asdict(source) for source in sources])
        response = client.converse(modelId=model, **request, inferenceConfig={'maxTokens': 512})
        record['stop_reason'] = response.get('stopReason')
        if response.get('stopReason') != 'end_turn':
            raise ValueError('Incomplete selector response')
        raw = ''.join(block.get('text', '') for block in response['output']['message']['content'])
        record['raw_output'] = raw
        selected, decision = resolve(parse_output(raw), pairs, documents, sources, question=question,
                                     country=country, language=language, active_ids=active_ids)
        record['validated_decision'] = decision
        record['selected_ids'] = [row['id'] for row, _ in selected]
        return selected
    except (ValueError, KeyError, TypeError) as exc:
        record['validation_error'] = str(exc)
        return []  # Invalid evidence is never replaced by unselected candidates.
