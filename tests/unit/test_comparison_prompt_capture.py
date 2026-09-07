"""Evaluation capture preserves actual candidate text without dumping SDK fields."""

from scripts.run_matched_chat_comparison import capture_converse_text


def test_capture_retains_exact_order_and_preview_boundary():
    text = 'Candidate 2\nText:\n' + 'x' * 1200 + '\n\nCandidate 1\nText:\nRule'
    request = {
        'system': [{'text': 'Select direct evidence'}, {'cachePoint': {'type': 'default'}}],
        'messages': [{'role': 'user', 'content': [{'text': text}]}],
    }
    captured = capture_converse_text(request)
    assert captured == {
        'system': ['Select direct evidence'],
        'messages': [{'role': 'user', 'text': [text]}],
    }


def test_capture_excludes_nontext_and_unknown_parameters():
    captured = capture_converse_text({
        'authorization': 'must-not-copy',
        'additionalModelRequestFields': {'opaque': 'must-not-copy'},
        'messages': [{'role': 'user', 'content': [
            {'text': 'Synthetic question'}, {'image': {'source': {'bytes': b'private'}}},
        ]}],
    })
    assert captured == {'system': [], 'messages': [{'role': 'user', 'text': ['Synthetic question']}]}
