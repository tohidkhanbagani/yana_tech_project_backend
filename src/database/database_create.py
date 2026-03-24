from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .database_tables import Base


BASE_DIR = Path(__file__).resolve().parent.parent.parent

DATA_DIRECTORY = BASE_DIR/"data"/"database"

if not DATA_DIRECTORY.exists():
    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATA_DIRECTORY/"yana.db"

DATABASE_URL = f"sqlite:///{str(DATABASE_PATH)}"

engine = create_engine(DATABASE_URL, future=True, echo=False, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    print("creating database.....")
    Base.metadata.create_all(bind=engine)
    print(f"database created successfully at {DATABASE_PATH}")

if __name__ == "__main__":
    init_db()