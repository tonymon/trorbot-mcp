from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Fiscal Data API
    fiscal_data_base_url: str = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"

    # Knowledge bases (Amazon S3 Vectors) — optional; KB tools gracefully degrade when unset
    trorbot_kb_bucket: str = ""
    trorbot_kb_aws_profile: str = ""
    trorbot_kb_region: str = "us-east-1"

    # Server
    mcp_transport: str = "stdio"
    # HTTP mode has no authentication, so it listens on this machine only unless HOST is set
    host: str = "127.0.0.1"
    port: int = 8080
    http_timeout: int = 30

    @property
    def kb_enabled(self) -> bool:
        return bool(self.trorbot_kb_bucket)


settings = Settings()
