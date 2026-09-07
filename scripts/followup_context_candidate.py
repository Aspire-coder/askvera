"""Isolated context-selection candidate; not used by the production chat path.

The target is a requested subject, never permission to retrieve foreign policy.
Callers must still apply the session market and document-scope access checks.
"""

from dataclasses import dataclass
from typing import Callable

from services.market_config import find_market_mentions

MAX_CONTEXT_QUESTIONS = 32
MAX_CONTEXT_CHARACTERS = 16_000


@dataclass(frozen=True)
class FollowupContext:
    current_question: str
    prior_questions: tuple[str, ...]
    target_markets: frozenset[str]


def resolve_context(
    current: str,
    prior_user_questions: list[str],
    *,
    is_dependent: Callable[[str], bool],
) -> FollowupContext:
    """Retain the latest topic chain and use the latest explicitly named target.

    Inputs must be user turns only, in chronological order. No model-generated
    answer is accepted as context or evidence. Dependence classification is
    supplied by the caller so this experiment does not change that variable.
    """
    if not current.strip():
        raise ValueError("A current question is required")
    characters = len(current)
    if characters > MAX_CONTEXT_CHARACTERS:
        raise ValueError("Follow-up context exceeds the experiment character limit")
    chain: list[str] = []
    if is_dependent(current):
        for question in reversed(prior_user_questions):
            if not question.strip():
                continue
            characters += len(question)
            if len(chain) >= MAX_CONTEXT_QUESTIONS or characters > MAX_CONTEXT_CHARACTERS:
                # Do not silently drop the anchor or an intervening target.
                raise ValueError("Follow-up context exceeds the experiment limit")
            chain.append(question)
            if not is_dependent(question):
                break
        chain.reverse()

    target = find_market_mentions(current)
    if not target:
        for question in reversed(chain):
            target = find_market_mentions(question)
            if target:
                break
    return FollowupContext(current, tuple(chain), frozenset(target))
