from __future__ import annotations

import json
import logging
import re

from agno.models.message import Message
from agno.models.response import ModelResponse
from pydantic import BaseModel

from src.agent.factory import build_classifier_model

logger = logging.getLogger(__name__)


class CommentClassification(BaseModel):
    sentiment: str
    is_pattern_correction: bool


_CLASSIFIER_SYSTEM_PROMPT = """\
You are a code-review comment classifier. Given a developer's comment on a pull request, output a JSON object with exactly two fields:

1. "sentiment": one of "positive", "negative", or "neutral".
   - "positive": the developer expresses agreement, gratitude, acknowledgement, or confirms they will act on the feedback.
   - "negative": the developer expresses disagreement, points out an error in the review, or rejects the suggestion.
   - "neutral": the comment is a question, clarification, or does not clearly express approval or disapproval.

2. "is_pattern_correction": true or false.
   - true: the developer is explaining how things are done in their project — describing conventions, architectural decisions, migration plans, preferred patterns, or correcting a misunderstanding about the codebase's standards.
   - false: the comment does not convey project-specific conventions or corrections about how things should be done.

Respond ONLY with the JSON object, no extra text. Work in any language.\
"""

_SAFE_DEFAULT = CommentClassification(sentiment="neutral", is_pattern_correction=False)


async def classify_comment(body: str) -> CommentClassification:
    try:
        model = build_classifier_model()
        messages = [
            Message(role="system", content=_CLASSIFIER_SYSTEM_PROMPT),
            Message(role="user", content=body),
        ]
        response: ModelResponse = await model.aresponse(
            messages=messages,
            response_format=CommentClassification,
        )

        if response.parsed is not None:
            return response.parsed  # type: ignore[no-any-return]

        raw = response.content or ""
        if isinstance(raw, list):
            raw = "".join(str(part) for part in raw)

        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())

        return CommentClassification.model_validate(json.loads(raw))
    except Exception:
        logger.warning("Comment classification failed, using safe defaults", exc_info=True)
        return _SAFE_DEFAULT
