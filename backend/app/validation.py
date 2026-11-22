"""Text validation without normalization: preserves historical event fingerprints."""
from pydantic import BaseModel, ConfigDict, field_validator


class SafeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    @field_validator('*')
    @classmethod
    def safe_text(cls, value):
        if isinstance(value,str):
            if '\x00' in value: raise ValueError('NUL not supported')
            value.encode('utf-8')
        return value
