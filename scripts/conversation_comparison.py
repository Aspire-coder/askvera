"""Local comparison recording; callers provide isolated, fully validated chat adapters.

An adapter returns the actual delivered response, never an intermediate draft.
This module does not call a model, authorize evidence or grade response quality.
"""
from copy import deepcopy


class ConversationRunError(RuntimeError):
    """Keep completed turns available when an adapter or response contract fails."""

    def __init__(self, records):
        super().__init__('Conversation comparison stopped; inspect partial records')
        self.records = deepcopy(records)


def compare_conversation(sequence, adapters):
    """Each arm receives only its own completed turns, with explicit locale state.

    Adapters accept keyword arguments request and history, returning a response
    dictionary with a nonempty answer and optional trace/citation fields. They
    must run normal routing and final validation before returning. On exceptions,
    partial records remain available on ConversationRunError; errors are not answers.
    """
    if set(adapters) != {'current', 'candidate'}:
        raise ValueError('Expected current and candidate adapters')
    turns = sequence['turns']
    if not isinstance(turns, list) or not 1 <= len(turns) <= 20:
        raise ValueError('Expected one to 20 turns')
    # Validate the complete sequence before invoking either adapter.
    for turn in turns:
        if not isinstance(turn, dict) or set(turn) != {'message', 'country', 'language', 'expected'}:
            raise ValueError('Invalid turn fields')
        if any(not isinstance(v, str) or not v.strip() for v in turn.values()):
            raise ValueError('Turn fields must be nonempty strings')
    records = {'id': sequence['id'], 'current': [], 'candidate': []}
    histories = {'current': [], 'candidate': []}
    for index, turn in enumerate(turns):
        request = {key: turn[key] for key in ('message', 'country', 'language')}
        for arm, adapter in adapters.items():
            history = deepcopy(histories[arm])
            try:
                response = adapter(request=deepcopy(request), history=deepcopy(history))
                if (not isinstance(response, dict) or not isinstance(response.get('answer'), str)
                        or not response['answer'].strip()):
                    raise ValueError('Adapter must return an actual delivered answer')
            except Exception as exc:
                # Preserve progress without treating a rejected draft or an error
                # message as a delivered turn. The caller decides how to persist.
                records[arm].append({'turn': index + 1, 'request': deepcopy(request), 'history': history,
                                     'error_type': type(exc).__name__, 'grade': 'execution_error'})
                raise ConversationRunError(records) from exc
            response = deepcopy(response)
            records[arm].append({'turn': index + 1, 'request': deepcopy(request), 'history': history,
                                 'response': response, 'expected': turn['expected'], 'grade': 'not_reviewed'})
            histories[arm].append({'request': deepcopy(request), 'answer': response['answer']})
    return records
