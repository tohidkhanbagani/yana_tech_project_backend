import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .database_tables import Base

# 1. Check for Render's environment variable first
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Fix for SQLAlchemy/PostgreSQL string compatibility
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    # Create the cloud engine (No check_same_thread needed for Postgres)
    engine = create_engine(DATABASE_URL, future=True, echo=False)
else:
    # 2. Local SQLite Fallback fallback so local operations don't break
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    DATA_DIRECTORY = BASE_DIR / "data" / "database"
    if not DATA_DIRECTORY.exists():
        DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH = DATA_DIRECTORY / "yana.db"
    DATABASE_URL = f"sqlite:///{str(DATABASE_PATH)}"
    
    engine = create_engine(DATABASE_URL, future=True, echo=False, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    print("Initializing database schema...")
    Base.metadata.create_all(bind=engine)
    print("Database tables synchronized successfully.")

if __name__ == "__main__":
    init_db()
