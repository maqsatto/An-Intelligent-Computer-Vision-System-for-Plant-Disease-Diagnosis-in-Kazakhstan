from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def make_sessions(engine):
    return sessionmaker(engine, expire_on_commit=False)
