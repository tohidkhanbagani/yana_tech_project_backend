import os
import logging
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.endpoints.websockets import manager
from fastapi import Request

# Endpoints mapping
from src.endpoints import auth, employees, projects, tasks, uploads, dashboard, attendance, websockets, clients, checklists

# Database mapping for Seeding
from src.database.database_create import SessionLocal, engine
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
    # Ensure all tables are created (Safe to call, won't drop existing data)
    Base.metadata.create_all(bind=engine)
    
    # Check for First-Time Setup
    with SessionLocal() as session:
        try:
            admin_count = session.query(Admins).count()
            if admin_count == 0:
                logger.info("SYSTEM INIT: No administrators found. Generating default SuperAdmin...")
                default_admin = Admins(
                    username="superadmin",
                    password=get_password_hash("DefaultPassword123!"),
                    email="systemadmin@yanaos.com",
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
    # Teardown logic (if any) goes here

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
        "https://yana-tech-project-frontend.vercel.app",
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
async def broadcast_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        if response.status_code >= 200 and response.status_code < 300:
            # We don't want to broadcast on login or file uploads generally, but doing it globally is safe enough for a small app.
            # Skip for login to prevent unnecessary broadcasts
            if "/auth/login" not in request.url.path:
                await manager.broadcast({"action": "REFRESH_WORKSPACE"})
    return response

if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn
    uvicorn.run("main:app", host="[IP_ADDRESS]", port=8001, reload=True)