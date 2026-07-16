import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from app.models import Base
from app.models.oa_views import VIEW_NAMES

target_metadata = Base.metadata


def get_database_url() -> str:
    """容器优先读取环境变量，本地维护命令继续兼容 alembic.ini。"""
    return os.getenv("ALEMBIC_DATABASE_URL") or config.get_main_option(
        "sqlalchemy.url"
    )

# Include schemas in autogenerate, but only compare objects in the 'oa' schema

def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name in VIEW_NAMES:
        return False
    if type_ == "table":
        return object.schema == "oa"
    if type_ == "index":
        return object.table.schema == "oa"
    if type_ == "foreign_key_constraint":
        return object.table.schema == "oa"
    if type_ == "unique_constraint":
        return object.table.schema == "oa"
    return True


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = create_engine(get_database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
