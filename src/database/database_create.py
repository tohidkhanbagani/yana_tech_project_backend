import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from .database_tables import Base


BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env
dotenv_path = BASE_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)

# Prefer DIRECT_URL (port 5432) to bypass PgBouncer circuit breaker and connection pooler limitations
DATABASE_URL = os.getenv("DIRECT_URL") or os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Strip any accidental whitespace or quotes that might have been pasted into the Render dashboard
    DATABASE_URL = DATABASE_URL.strip().strip('"').strip("'")
    
    # Check if the database URL has the password placeholder
    if "[YOUR-PASSWORD]" in DATABASE_URL:
        print("\n" + "="*80)
        print("WARNING: The DATABASE_URL in your .env file contains the placeholder '[YOUR-PASSWORD]'.")
        print("Please replace '[YOUR-PASSWORD]' with your actual Supabase database password in the .env file.")
        print("Falling back to local SQLite database for now to prevent the application from crashing.")
        print("="*80 + "\n")
        
        # Fallback to SQLite
        DATA_DIRECTORY = BASE_DIR / "data" / "database"
        if not DATA_DIRECTORY.exists():
            DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
        DATABASE_PATH = DATA_DIRECTORY / "yana.db"
        DATABASE_URL = f"sqlite:///{str(DATABASE_PATH)}"
        engine = create_engine(DATABASE_URL, future=True, echo=False, connect_args={"check_same_thread": False})
    else:
        # Fix for SQLAlchemy/PostgreSQL string compatibility if it starts with postgres://
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
            
        # Clean pgbouncer parameters since psycopg2/libpq does not support them
        DATABASE_URL = DATABASE_URL.replace("?pgbouncer=true", "").replace("&pgbouncer=true", "")
            
        # Create engine for cloud Postgres database (no check_same_thread)
        engine = create_engine(DATABASE_URL, future=True, echo=False)
else:
    # Local SQLite Fallback
    DATA_DIRECTORY = BASE_DIR / "data" / "database"
    if not DATA_DIRECTORY.exists():
        DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH = DATA_DIRECTORY / "yana.db"
    DATABASE_URL = f"sqlite:///{str(DATABASE_PATH)}"
    engine = create_engine(DATABASE_URL, future=True, echo=False, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    print("initializing database.....")
    Base.metadata.create_all(bind=engine)
    print("database initialized successfully")

if __name__ == "__main__":
    init_db()
