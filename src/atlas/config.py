from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    eia_api_key: str = ""
    census_api_key: str = ""
    sec_contact_email: str = ""
