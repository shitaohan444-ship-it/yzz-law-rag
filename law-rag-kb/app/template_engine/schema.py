from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SourceBinding(BaseModel):
    table_index: int = Field(ge=0)
    anchor: str = Field(min_length=1)
    occurrence: int = Field(default=0, ge=0)
    mode: Literal["text", "multiline", "checkbox"] = "text"
    target_cell_offset: int = Field(default=0, ge=0)
    target_paragraph: int = Field(default=0, ge=0)
    append_paragraph: bool = False


class TemplateField(BaseModel):
    field_id: str = Field(pattern=r"^[a-z][a-z0-9_.\[\]-]+$")
    label: str
    value_type: Literal[
        "string", "date", "money", "enum", "boolean", "party_ref", "list"
    ]
    required_policy: Literal["required", "conditional", "optional", "computed"]
    source_policy: list[Literal["oa", "material", "evidence", "user", "computed"]]
    generation_policy: Literal[
        "extract_only", "compute_only", "draft_with_sources", "user_only"
    ]
    missing_behavior: Literal["pause", "blank", "confirm", "not_applicable"]
    sensitivity: Literal["normal", "personal", "sensitive"] = "normal"
    binding: SourceBinding


class TemplateSchema(BaseModel):
    schema_id: str
    version: str
    template_code: str
    document_type: str
    cause_code: str
    party_role: str
    source_path: str
    parser_version: str = "template-compiler-v1"
    fields: list[TemplateField]
    sections: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_field_ids(self):
        ids = [field.field_id for field in self.fields]
        if len(ids) != len(set(ids)):
            raise ValueError("field_id must be unique")
        return self

    @property
    def required_fields(self) -> set[str]:
        return {
            field.field_id
            for field in self.fields
            if field.required_policy == "required" and field.missing_behavior == "pause"
        }


def load_schema(path: str | Path) -> TemplateSchema:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return TemplateSchema.model_validate(data)
