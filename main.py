# Initialize environment and auto-generate SECRET_KEY if missing
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
dotenv_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=dotenv_path)

secret_key = os.getenv("SECRET_KEY")
if not secret_key or secret_key == "yana-super-secret-key-change-this-in-production":
    new_key = secrets.token_hex(32)
    os.environ["SECRET_KEY"] = new_key
    content = ""
    if dotenv_path.exists():
        content = dotenv_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith("SECRET_KEY="):
            lines[i] = f"SECRET_KEY={new_key}"
            found = True
            break
    if not found:
        lines.append(f"SECRET_KEY={new_key}")
    dotenv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

from openpyxl.descriptors import String
import logging
from contextlib import asynccontextmanager
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.responses import JSONResponse
# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore [missing-import]
from src.endpoints.websockets import manager
# pyrefly: ignore [missing-import]
from fastapi import Request
# pyrefly: ignore [missing-import]
from sqlalchemy import text

# Endpoints mapping
from src.endpoints import auth, employees, projects, tasks, uploads, dashboard, attendance, websockets, clients, checklists

# Database mapping for Seeding
from src.database.database_create import SessionLocal, engine
# pyrefly: ignore [missing-import]
from src.database.database_tables import Base, Admins

# FIX: Import get_password_hash from database_operations instead of auth
from src.database.database_operations import get_password_hash

# Setup Base Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Yana_Main_App")
 
# --- Ensure Data Directory Exists ---
if not os.path.exists("data"):
    os.makedirs("data", exist_ok=True)
    logger.info("SYSTEM INIT: 'data' directory created.")

# ==========================================
#       AUTO-SEEDING STARTUP SCRIPT
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP LOGIC ---
    # Ensure all tables are created (Safe to call, won't drop existing data)
    Base.metadata.create_all(bind=engine)

    # Run runtime migrations for database schema upgrades
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE admins ADD COLUMN current_session_id VARCHAR"))
            conn.commit()
            logger.info("SYSTEM STARTUP MIGRATION: Added current_session_id column to admins table.")
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE employees ADD COLUMN current_session_id VARCHAR"))
            conn.commit()
            logger.info("SYSTEM STARTUP MIGRATION: Added current_session_id column to employees table.")
        except Exception:
            pass

    with SessionLocal() as session:
        try:
            admin_count = session.query(Admins).count()
            if admin_count == 0:
                logger.info("SYSTEM INIT: No administrators found. Generating default SuperAdmin...")
                default_admin = Admins(
                    username="superadmin",
                    password=get_password_hash("DefaultPassword123!"),
                    email="[EMAIL_ADDRESS]",
                    full_name="SuperAdmin",
                    access_level="SystemAdmin"
                )
                session.add(default_admin)
                session.commit()
                logger.info("SYSTEM INIT SUCCESS: SuperAdmin generated. Username: superadmin | Password: DefaultPassword123!")
            else:
                logger.info(f"System Check: Database contains {admin_count} Administrator(s). Ready.")
        except Exception as e:
            logger.error(f"Failed to run initialization checks: {str(e)}", exc_info=True)
            
    yield # App is running
    
    # --- TEARDOWN / SHUTDOWN LOGIC ---
    logger.info("Shutting down application. Disposing database connection pool...")
    try:
        # This safely closes all pooled connections when the server stops
        engine.dispose()
        logger.info("Database engine disposed successfully.")
    except Exception as e:
        logger.error(f"Error during engine disposal: {str(e)}")

# ==========================================
#              APP INITIALIZATION
# ==========================================
app = FastAPI(
    title="Yana OS Operations & Management API",
    description="Sophisticated REST API with strict JWT Role Auth for Yana's Enterprise Ecosystem.",
    version="2.0.0",
    lifespan=lifespan # Attaches the startup script to the application
)

# --- CORS MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://yana-frontend.vercel.app",
        "http://localhost:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (OPTIONS, GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers 
)

# --- ROUTER INCLUSIONS ---
app.mount("/data", StaticFiles(directory="data"), name="data")
app.include_router(auth.router)
# app.include_router(users.router) # Keep if legacy operations remain, otherwise can be deprecated
app.include_router(tasks.router)
app.include_router(projects.router)
app.include_router(employees.router)
app.include_router(uploads.router)
app.include_router(dashboard.router) # The new Phase 5 Lightning Fast Dashboard
app.include_router(attendance.router)
app.include_router(clients.router)
app.include_router(websockets.router)
app.include_router(checklists.router)



@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = "upgrade-insecure-requests"
    return response

@app.middleware("http")
async def broadcast_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        if response.status_code >= 200 and response.status_code < 300:
            # We don't want to broadcast on login or file uploads generally, but doing it globally is safe enough for a small app.
            # Skip for login to prevent unnecessary broadcasts
            if "/auth/login" not in request.url.path:
                import asyncio
                asyncio.create_task(manager.broadcast({"action": "REFRESH_WORKSPACE"}))
    return response

# @app.middleware("http")
# async def db_connection_cleanup_middleware(request: Request, call_next):
#     try:
#         response = await call_next(request)
#         return response
#     finally:
#         try:
#             from src.database.database_create import engine, DATABASE_URL
#             if DATABASE_URL and isinstance(DATABASE_URL, str) and DATABASE_URL.startswith("postgres"):
#                 engine.dispose(close_all_connections=False)
#         except Exception as e:
#             logger.error(f"Error disposing database engine: {str(e)}")

if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)