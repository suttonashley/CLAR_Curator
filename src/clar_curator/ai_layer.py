"""
AI layer — use Claude to interpret a design document and produce an IntegrationSpec.

The prompt is kept deliberately schema-agnostic here. Once you've inspected your
sample .clar files and updated IntegrationSpec (and the generator templates), you
can tighten the system prompt and output schema accordingly.
"""

from __future__ import annotations

import json
import os

import anthropic
from pydantic import BaseModel

from clar_curator.generator.clar_generator import IntegrationSpec


# ---------------------------------------------------------------------------
# Pydantic schema for structured output
# ---------------------------------------------------------------------------

class FieldMapping(BaseModel):
    source: str
    target: str
    transform: str = ""


class IntegrationSpecSchema(BaseModel):
    name: str
    description: str
    version: str
    source_system: str
    target_system: str
    field_mappings: list[FieldMapping]
    xslt: str
    delivery_type: str
    delivery_config: dict


SYSTEM_PROMPT = """You are an expert Workday Studio integration developer.

Your task is to analyse a design document and extract a structured integration
specification that can be used to auto-generate a Workday Studio .clar file.

Rules:
- Extract the integration name, source system, target system, and all field
  mappings with any transformation logic described.
- If the design doc describes XSLT, include the full XSLT string in the `xslt`
  field; otherwise leave it empty.
- For `delivery_type` choose one of: SFTP, FTP, FTPS, HTTPS, EIB.
- For `delivery_config` include any host, port, path, credentials placeholder,
  or scheduling info mentioned in the doc.
- If information is missing or ambiguous, use sensible Workday Studio defaults
  and note the assumption in `description`.
- Return ONLY valid JSON — no prose, no markdown fences.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_spec(document_text: str, *, model: str = "claude-opus-4-6") -> IntegrationSpec:
    """
    Send document_text to Claude and return a populated IntegrationSpec.

    Args:
        document_text: Full text of the design document (from the parsers).
        model: Claude model ID to use.

    Returns:
        An IntegrationSpec ready for the generator.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    # Use streaming + adaptive thinking for potentially long design docs
    with client.messages.stream(
        model=model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Here is the integration design document:\n\n"
                    f"{document_text}\n\n"
                    "Return the structured integration spec as JSON."
                ),
            }
        ],
    ) as stream:
        final = stream.get_final_message()

    # Extract text block (thinking blocks are skipped)
    raw_json = next(
        block.text for block in final.content if block.type == "text"
    )

    parsed = IntegrationSpecSchema.model_validate_json(raw_json)

    return IntegrationSpec(
        name=parsed.name,
        description=parsed.description,
        version=parsed.version,
        source_system=parsed.source_system,
        target_system=parsed.target_system,
        field_mappings=[m.model_dump() for m in parsed.field_mappings],
        xslt=parsed.xslt,
        delivery_type=parsed.delivery_type,
        delivery_config=parsed.delivery_config,
    )
