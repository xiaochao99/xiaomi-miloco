# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Model data models
Define model-related data structures
"""


from typing import Optional
from pydantic import BaseModel, Field


class ModelLoadRequest(BaseModel):
    local_model_name: str = Field(..., description="Local model name")
    load: bool = Field(..., description="Whether to load")

class ThirdPartyModelVendor(BaseModel):
    base_url: str = Field(..., description="Base URL, reference OpenAI, https://api.openai.com/v1")
    api_key: str = Field(..., description="API key")


class ThirdPartyModelInfo(ThirdPartyModelVendor):
    id: Optional[str] = Field(None, description="Model access point ID")
    model_name: str = Field(..., description="Model name")


class ThirdPartyModelCreate(ThirdPartyModelVendor):
    model_names: list[str] = Field(..., description="Model name list")

    def convert_to_model_infos(self) -> list[ThirdPartyModelInfo]:
        return [
            ThirdPartyModelInfo(
                model_name=model_name,
                id=None,
                base_url=self.base_url,
                api_key=self.api_key
            )
            for model_name in self.model_names
        ]


class LLMModelInfo(ThirdPartyModelInfo):
    local: bool = Field(default=False, description="Whether it is a local model")
    loaded: bool = Field(default=False, description="Whether it is loaded")
    estimate_vram_usage: float = Field(default=-1.0, description="Estimated VRAM usage (GB)")

    @classmethod
    def from_third_party(cls, third_party_model_info: ThirdPartyModelInfo) -> "LLMModelInfo":
        return cls(
            id=third_party_model_info.id,
            model_name=third_party_model_info.model_name,
            base_url=third_party_model_info.base_url,
            api_key=third_party_model_info.api_key,
            local=False,
            loaded=True,
            estimate_vram_usage=-1.0
        )

class ModelsList(BaseModel):
    models: list[LLMModelInfo] = Field(..., description="Third-party model list")
    current_model: dict[str, str] = Field(..., description="Current scenario and corresponding model ID")


class ModelPurposeInfo(BaseModel):
    type: str = Field(..., description="Model purpose type")
