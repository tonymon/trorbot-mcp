from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Fiscal Data API
    fiscal_data_base_url: str = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"

    # TRORBOT API Gateway — optional; KB tools gracefully degrade when unset
    trorbot_api_url: str = ""
    trorbot_api_key: str = ""

    # Server
    mcp_transport: str = "stdio"
    port: int = 8080
    http_timeout: int = 30

    @property
    def kb_enabled(self) -> bool:
        return bool(self.trorbot_api_url and self.trorbot_api_key)


settings = Settings()
