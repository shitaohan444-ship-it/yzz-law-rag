from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL
    postgres_db: str = "law_rag"
    postgres_user: str = "law_rag_user"
    postgres_password: str = "law_rag_password"
    postgres_port: int = 5432
    postgres_host: str = "localhost"

    # MinIO
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin123"
    minio_host: str = "localhost"
    minio_api_port: int = 9000
    minio_secure: bool = False
    minio_bucket_name: str = "law-firm-files"

    # Project
    project_name: str = "law-rag-service"
    env: str = "local"

    # Schema for OA module
    db_schema: str = "oa"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_with_search_path(self) -> str:
        # 逗号在 options 中需要编码为 %2C，否则 PostgreSQL 会按参数分隔解析
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            f"?options=-c%20search_path%3D{self.db_schema}%2Cpublic"
        )


settings = Settings()
