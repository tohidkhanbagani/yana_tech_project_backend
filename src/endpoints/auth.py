from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
import json
import logging

from src.database.database_operations import DatabaseOperations
from src.database.database_create import SessionLocal
from src.database.database_tables import Admins, Employees

# Professional logging setup
logger = logging.getLogger("Yana_Auth_Router")

db = DatabaseOperations()

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

# ==========================================
#              AUTH CONFIGURATION
# ==========================================

import os
SECRET_KEY = os.getenv("SECRET_KEY", "yana-super-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480 # Extended to 8 hours for workday comfort

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ==========================================
#        CENTRALIZED ERROR HANDLER
# ==========================================

def handle_response(result_str: str):
    """
    Extremely robust response parser. Evaluates the JSON string returned from 
    DatabaseOperations, catches DB-level errors, and maps them to proper HTTP Exceptions.
    """
    if not result_str:
        logger.error("Database returned an empty response string.")
        raise HTTPException(status_code=500, detail="Empty response from database layer.")
    
    try:
        result = json.loads(result_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse database JSON response: {result_str} | Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Invalid JSON response format from database.")

    # Only process error fields if the response is a dictionary
    if isinstance(result, dict):
        if "error" in result and result["error"]:
            error_msg = str(result["error"]).lower()
            status_code = 404 if "not found" in error_msg else 400
            raise HTTPException(status_code=status_code, detail=result["error"])
        
        if "critical_error" in result:
            logger.critical(f"Database CRITICAL ERROR: {result['critical_error']}")
            raise HTTPException(status_code=500, detail=result["critical_error"])
            
    return result


# ==========================================
#         CURRENT USER DEPENDENCY
# ==========================================

def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Decodes JWT token and intelligently determines whether to fetch an Admin or an Employee 
    based on the payload signature. Rejects invalid or expired tokens immediately.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or session expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_role: str = payload.get("role")
        user_id: str = payload.get("id")
        
        if username is None or user_role is None or user_id is None:
            raise credentials_exception
            
    except JWTError as e:
        logger.warning(f"JWT Decode Error: {str(e)}")
        raise credentials_exception
        
    with SessionLocal() as session:
        try:
            # 1. Admin Verification
            if user_role.lower() == "admin":
                user = session.query(Admins).filter(Admins.id == user_id).first()
                if user is None:
                    raise credentials_exception
                return {"id": user.id, "username": user.username, "role": "admin", "access_level": user.access_level}
                
            # 2. Employee Verification
            elif user_role.lower() == "employee":
                user = session.query(Employees).filter(Employees.id == user_id).first()
                if user is None or not user.is_active:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Employee account is disabled or missing.")
                return {"id": user.id, "username": user.username, "role": "employee"}
                
            else:
                raise credentials_exception
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching current user from DB: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error during user validation.")


# ==========================================
#              AUTH ENDPOINTS
# ==========================================

@router.post("/login", tags=["Authentication"])
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Unified Login Endpoint.
    Intelligently checks the Admins table first, and falls back to the Employees table.
    Logs every login attempt accurately into the LoginHistory table.
    """
    try:
        with SessionLocal() as session:
            client_ip = request.client.host if request.client else "Unknown"
            user_agent = request.headers.get("User-Agent", "Unknown")

            # 1. Check Admins Table
            admin = session.query(Admins).filter(Admins.username == form_data.username).first()
            if admin and verify_password(form_data.password, admin.password):
                
                # Log success & Generate Token
                db.log_login_history(user_id=admin.id, user_role="Admin", ip_address=client_ip, user_agent=user_agent)
                token_data = {"sub": admin.username, "id": admin.id, "role": "admin", "access_level": admin.access_level}
                access_token = create_access_token(data=token_data, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
                
                return {"access_token": access_token, "token_type": "bearer"}

            # 2. Check Employees Table
            employee = session.query(Employees).filter(Employees.username == form_data.username).first()
            if employee and verify_password(form_data.password, employee.password):
                
                if not employee.is_active:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account has been deactivated. Contact HR.")

                # Log success & Generate Token
                db.log_login_history(user_id=employee.id, user_role="Employee", ip_address=client_ip, user_agent=user_agent)
                token_data = {"sub": employee.username, "id": employee.id, "role": "employee"}
                access_token = create_access_token(data=token_data, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
                
                return {"access_token": access_token, "token_type": "bearer"}

            # 3. Failed Authentication
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failure processing error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal authentication server error.")

@router.get("/me", tags=["Authentication"])
def read_users_me(current_user: dict = Depends(get_current_user)):
    """Returns the currently logged in user's profile info directly from the verified token mapping."""
    return current_user