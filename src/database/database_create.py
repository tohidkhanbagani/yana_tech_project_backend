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
        engine = create_engine(DATABASE_URL, 
        future=True, 
        echo=False, 
        connect_args={"check_same_thread": False},
        # pool_recycle=600,     # Discard connections older than 10 mins (Supabase defaults drop idle links)
        # pool_pre_ping=True    # Test connection before giving it to the app
        )
    else:
        # Fix for SQLAlchemy/PostgreSQL string compatibility if it starts with postgres://
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
            
        # Clean pgbouncer parameters since psycopg2/libpq does not support them
        DATABASE_URL = DATABASE_URL.replace("?pgbouncer=true", "").replace("&pgbouncer=true", "")

        # Auto-correct Supabase pooler URLs using port 5432 (Session Mode) to direct connections.
        # Session Mode has a strict limit of 15 connections, causing EMAXCONNSESSION errors.
        # Direct connection (port 5432 on db.[project-ref].supabase.co) allows up to 60 connections.
        if "pooler.supabase.com:5432" in DATABASE_URL:
            import re
            match = re.search(r"//([^:]+):", DATABASE_URL)
            if match:
                user_part = match.group(1)
                if "." in user_part:
                    project_ref = user_part.split(".")[-1]
                    old_host_port = re.search(r"@([^:/]+):5432", DATABASE_URL)
                    if old_host_port:
                        old_host = old_host_port.group(1)
                        new_host = f"db.{project_ref}.supabase.co"
                        DATABASE_URL = DATABASE_URL.replace(old_host, new_host)
                        print(f"Auto-correcting Supabase Pooler session mode URL to direct URL: host changed to {new_host}")
            
        # Create engine for cloud Postgres database (no check_same_thread)
        engine = create_engine(
            DATABASE_URL,
            future=True,
            echo=False,
            pool_size=20,
            max_overflow=10,
            pool_timeout=15,
            pool_recycle=600,
            pool_pre_ping=True
        )
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
