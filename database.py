import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Render se URL uthayega
SQLALCHEMY_DATABASE_URL = os.getenv("postgresql://war_db_user:I7g7HY7FFcORKIbC7aQfoaunN9vPTypl@dpg-d8fqti9kh4rs73ct4sj0-a/war_db")

# Agar local pe ho toh fallback
if not SQLALCHEMY_DATABASE_URL:
    SQLALCHEMY_DATABASE_URL = "sqlite:///./war_project.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()