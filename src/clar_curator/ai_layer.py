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

from clar_curator.generator.clar_generator import IntegrationSpec, LaunchParam, ServiceAttribute


# ---------------------------------------------------------------------------
# Pydantic schema for structured output
# ---------------------------------------------------------------------------

class FieldMapping(BaseModel):
    source: str
    target: str
    transform: str = ""


class LaunchParamSchema(BaseModel):
    name: str
    type: str = "text"
    default_wid: str = ""
    default_desc: str = ""


class ServiceAttributeSchema(BaseModel):
    name: str
    type: str = "text"
    display_as_password: bool = False
    required_for_launch: bool = False


class IntegrationSpecSchema(BaseModel):
    name: str
    description: str = ""
    author: str = ""
    assembly_version: str = "2021.51"
    int_sys_name: str = ""
    attribute_map_service_name: str = ""
    launch_params: list[LaunchParamSchema] = []
    attributes: list[ServiceAttributeSchema] = []
    xslt: str = ""
    source_system: str = ""
    target_system: str = ""
    version: str = "1.0"
    field_mappings: list[FieldMapping] = []
    delivery_type: str = "HTTPS"
    delivery_config: dict = {}


SYSTEM_PROMPT = """You are an expert Workday Studio integration developer.

Your task is to analyse a design document and extract a structured integration
specification that can be used to auto-generate a Workday Studio .clar file.

Rules:
- `name`: use underscores, no spaces (e.g. "Greenhouse_Hire_Inbound").
- `int_sys_name`: the full integration system name as it appears in Workday
  (e.g. "INT042 STU Greenhouse Hire Inbound"). Include the INT number and
  tenant prefix if mentioned, otherwise infer a sensible default.
- `attribute_map_service_name`: the named attribute-map service (e.g.
  "Greenhouse-Connection"). Infer from the design doc or default to
  "{name}-Connection".
- `launch_params`: list all launch parameters (date ranges, filters, etc.).
  For each include name, type (text/date/boolean/number), and optionally
  default_wid / default_desc if a Workday class-report-field default is
  described.
- `attributes`: list all connection/config attributes on the attribute-map
  service. Set display_as_password=true for secrets/tokens/passwords, and
  required_for_launch=true for credentials needed at runtime.
- `xslt`: include the full XSLT string only if the design doc explicitly
  describes XSLT transformation logic; otherwise leave empty.
- `delivery_type`: one of SFTP, FTP, FTPS, HTTPS, EIB.
- `delivery_config`: any host, port, path, or scheduling info from the doc.
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
        author=parsed.author,
        assembly_version=parsed.assembly_version,
        int_sys_name=parsed.int_sys_name,
        attribute_map_service_name=parsed.attribute_map_service_name,
        launch_params=[
            LaunchParam(
                name=p.name,
                type=p.type,
                default_wid=p.default_wid,
                default_desc=p.default_desc,
            )
            for p in parsed.launch_params
        ],
        attributes=[
            ServiceAttribute(
                name=a.name,
                type=a.type,
                display_as_password=a.display_as_password,
                required_for_launch=a.required_for_launch,
            )
            for a in parsed.attributes
        ],
        xslt=parsed.xslt,
        source_system=parsed.source_system,
        target_system=parsed.target_system,
        version=parsed.version,
        field_mappings=[m.model_dump() for m in parsed.field_mappings],
        delivery_type=parsed.delivery_type,
        delivery_config=parsed.delivery_config,
    )
