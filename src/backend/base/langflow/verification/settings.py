"""Explicit service configuration, isolated from Langflow's platform database."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_TOKEN_LENGTH = 16


class FlowSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VERIFICATION_", extra="ignore")

    internal_token: SecretStr
    api_url: str = "http://verification-api:8080"
    settlement_url: str = "http://verification-demo:8090"
    imaging_url: str = "http://verification-demo:8090"
    imaging_token: SecretStr = SecretStr("")
    imaging_timezone: str = "Asia/Shanghai"
    model_url: str = "http://verification-demo:8090"
    upstream_token: SecretStr = SecretStr("")
    request_timeout: float = Field(default=30, gt=0, le=600)
    demo_mode: bool = False

    @field_validator("imaging_timezone")
    @classmethod
    def valid_imaging_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


class VerificationSettings(FlowSettings):
    database_url: SecretStr
    database_schema: str = Field(default="verification", pattern=r"^[a-z][a-z0-9_]*$")
    clients: dict[str, SecretStr]
    langflow_url: str = "http://langflow:7860"
    langflow_api_key: SecretStr = SecretStr("")
    poll_interval: float = Field(default=2, gt=0, le=60)

    @model_validator(mode="after")
    def distinct_credentials(self) -> VerificationSettings:
        tokens = [v.get_secret_value() for v in self.clients.values()]
        internal = self.internal_token.get_secret_value()
        if not tokens or any(len(t) < MIN_TOKEN_LENGTH for t in [*tokens, internal]):
            msg = "Client and internal tokens must be configured with at least 16 characters"
            raise ValueError(msg)
        if len(set(tokens)) != len(tokens) or internal in tokens:
            msg = "Each source and the internal service must use distinct credentials"
            raise ValueError(msg)
        return self
