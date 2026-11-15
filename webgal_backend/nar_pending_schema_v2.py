"""Pydantic request validation (kept separate from MySQL-only ledger helpers)."""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClarificationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    clarification_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    selected_option_ids: list[str] = Field(default_factory=list, max_length=4)
    custom_text: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def has_value(self):
        if not self.selected_option_ids and not self.custom_text:
            raise ValueError("Select an option or explain your choice")
        if len(self.selected_option_ids) != len(set(self.selected_option_ids)):
            raise ValueError("Duplicate selected options")
        return self
