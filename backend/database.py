
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base

# Local development can use backend/.env. Render supplies its own environment
# variables, which must take precedence over values in that file.
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH, override=False)

database_url = os.getenv("DATABASE_URL")
if database_url:
    # Render provides postgres:// or postgresql:// URLs; SQLAlchemy uses the
    # psycopg 3 dialect explicitly here.
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
else:
    mysql_user = os.getenv("MYSQL_USER")
    mysql_password = os.getenv("MYSQL_PASSWORD")
    database_name = os.getenv("DATABASE_NAME")
    if not mysql_user or not mysql_password or not database_name:
        raise ValueError("Set DATABASE_URL or MYSQL_USER, MYSQL_PASSWORD, and DATABASE_NAME")
    database_url = URL.create(
        drivername="mysql+pymysql",
        username=mysql_user,
        password=mysql_password,
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=database_name,
    )

# Create SQLAlchemy engine
engine = create_engine(
    database_url,
    pool_pre_ping=True,
)

# Base class for database models
Base = declarative_base()


# Test MySQL connection
def test_connection():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        print("MySQL connected successfully!")

    except Exception as e:
        print("MySQL connection failed:", repr(e))
        raise
