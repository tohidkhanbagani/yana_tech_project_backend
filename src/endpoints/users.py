from fastapi import APIRouter, Depends, HTTPException
from schemas import UserCreate, UserUpdate
from src.database.database_operations import DatabaseOperations
from src.database.database_create import SessionLocal
from src.database.database_tables import User as DBUser
from src.endpoints.auth import get_current_user, handle_response


router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


db = DatabaseOperations()





@router.get("/get_all", tags=["Users"])
def get_all_users(current_user: dict = Depends(get_current_user)):
    response = db.get_all_users()
    return handle_response(response)

@router.get("/get/{user_id}", tags=["Users"])
def get_user(user_id: str, current_user: dict = Depends(get_current_user)):
    response = db.get_user(user_id)
    return handle_response(response)

@router.put("/update/{user_id}", tags=["Users"])
def update_user(user_id: str, user: UserUpdate, current_user: dict = Depends(get_current_user)):
    data = user.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No data provided to update.")
    if "password" in data:
        data["password"] = get_password_hash(data["password"])
    response = db.edit_user(user_id, data)
    return handle_response(response)

@router.delete("/delete/{user_id}", tags=["Users"])
def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    response = db.delete_user(user_id)
    return handle_response(response)


