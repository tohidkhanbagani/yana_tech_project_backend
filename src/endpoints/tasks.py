from fastapi import APIRouter, Depends, HTTPException
import logging
from schemas import (
    DeveloperTaskCreate, DeveloperTaskUpdate,
    ContentTaskCreate, ContentTaskUpdate
)
from src.database.database_operations import DatabaseOperations
from src.endpoints.auth import get_current_user, handle_response

logger = logging.getLogger("Yana_Tasks_Router")
router = APIRouter(prefix="/tasks", tags=["Timesheets & Tasks"])
db = DatabaseOperations()

# ==========================================
#          DEVELOPER TASKS
# ==========================================

from typing import List
import json

@router.post("/developer/batch-create", tags=["Timesheets & Tasks"])
def create_developer_task_batch(tasks: List[DeveloperTaskCreate], current_user: dict = Depends(get_current_user)):
    try:
        results = []
        for task in tasks:
            data = task.model_dump(exclude_unset=True)
            if current_user.get("role") != "admin":
                data["employee_id"] = current_user.get("id")
                
            response = db.add_developer_task(data)
            
            # Since db.add_developer_task returns stringified JSON, parse it back to dict 
            # to prevent double stringification issues, or handle error strings.
            resp_dict = json.loads(response)
            if "error" in resp_dict:
                raise HTTPException(status_code=400, detail=resp_dict["error"])
            results.append(resp_dict)
            
        return handle_response(json.dumps(results))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in create_developer_task_batch: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit batch developer timesheets.")

@router.post("/developer/create", tags=["Timesheets & Tasks"])
def create_developer_task(task: DeveloperTaskCreate, current_user: dict = Depends(get_current_user)):
    try:
        data = task.model_dump(exclude_unset=True)
        # Security: Force the employee_id to be the currently logged in user unless an Admin is overriding
        if current_user.get("role") != "admin":
            data["employee_id"] = current_user.get("id")
            
        response = db.add_developer_task(data)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in create_developer_task: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit developer timesheet.")

@router.put("/developer/update/{task_id}", tags=["Timesheets & Tasks"])
def update_developer_task(task_id: str, task: DeveloperTaskUpdate, current_user: dict = Depends(get_current_user)):
    try:
        data = task.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No data provided to update.")
        
        response = db.edit_developer_task(task_id, data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in update_developer_task: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update developer timesheet.")


# ==========================================
#        CONTENT CREATOR TASKS
# ==========================================

@router.post("/content/batch-create", tags=["Timesheets & Tasks"])
def create_content_task_batch(tasks: List[ContentTaskCreate], current_user: dict = Depends(get_current_user)):
    try:
        results = []
        for task in tasks:
            data = task.model_dump(exclude_unset=True)
            if current_user.get("role") != "admin":
                data["employee_id"] = current_user.get("id")
                
            response = db.add_content_creator_task(data)
            
            resp_dict = json.loads(response)
            if "error" in resp_dict:
                raise HTTPException(status_code=400, detail=resp_dict["error"])
            results.append(resp_dict)
            
        return handle_response(json.dumps(results))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in create_content_task_batch: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit batch content timesheets.")

@router.post("/content/create", tags=["Timesheets & Tasks"])
def create_content_task(task: ContentTaskCreate, current_user: dict = Depends(get_current_user)):
    try:
        data = task.model_dump(exclude_unset=True)
        # Security: Force the employee_id to be the currently logged in user unless an Admin is overriding
        if current_user.get("role") != "admin":
            data["employee_id"] = current_user.get("id")
            
        response = db.add_content_creator_task(data)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in create_content_task: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit content creator timesheet.")

@router.put("/content/update/{task_id}", tags=["Timesheets & Tasks"])
def update_content_task(task_id: str, task: ContentTaskUpdate, current_user: dict = Depends(get_current_user)):
    try:
        data = task.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No data provided to update.")
        
        response = db.edit_content_creator_task(task_id, data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in update_content_task: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update content timesheet.")


# ==========================================
#          UNIFIED TASK QUERIES
# ==========================================

@router.get("/all", tags=["Timesheets & Tasks"])
def get_all_tasks(current_user: dict = Depends(get_current_user)):
    """Fetches ALL tasks across BOTH tables. Generally for Admins & Dashboard."""
    try:
        response = db.get_all_tasks()
        data = handle_response(response)
        # RBAC: Strip restricted financial data for ManagerAdmin
        if current_user.get("access_level") == "ManagerAdmin" and isinstance(data, list):
            for task in data:
                task.pop("employee_cost", None)
                task.pop("billing_amount", None)
                task.pop("profit_loss", None)
        return data
    except Exception as e:
        logger.error(f"Router Error in get_all_tasks: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve universal task list.")

@router.get("/get/{task_id}", tags=["Timesheets & Tasks"])
def get_task(task_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_task(task_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_task: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve task details.")

@router.get("/get_by_employee/{employee_id}", tags=["Timesheets & Tasks"])
def get_tasks_by_employee(employee_id: str, current_user: dict = Depends(get_current_user)):
    """Fetches all tasks linked to a specific employee, pulling from both Task tables."""
    # Security: Ensure employees can only view their own tasks, but Admins can view anyone's
    if current_user.get("role") != "admin" and current_user.get("id") != employee_id:
        raise HTTPException(status_code=403, detail="You do not have permission to view another employee's tasks.")

    try:
        response = db.get_tasks_by_employee(employee_id)
        data = handle_response(response)
        # RBAC: Strip restricted financial data for ManagerAdmin
        if current_user.get("access_level") == "ManagerAdmin" and isinstance(data, list):
            for task in data:
                task.pop("employee_cost", None)
                task.pop("billing_amount", None)
                task.pop("profit_loss", None)
        return data
    except Exception as e:
        logger.error(f"Router Error in get_tasks_by_employee: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve employee task history.")

@router.delete("/delete/{task_id}", tags=["Timesheets & Tasks"])
def delete_task(task_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.delete_task(task_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in delete_task: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete task.")