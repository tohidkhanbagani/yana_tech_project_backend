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


# ==========================================
#          UNIFIED TASK QUERIES
# ==========================================

# ==========================================
#          UNIFIED TASK QUERIES
# ==========================================

@router.get("/all", tags=["Timesheets & Tasks"])
def get_all_tasks(current_user: dict = Depends(get_current_user)):
    """Fetches ALL tasks across BOTH tables. Generally for Admins & Dashboard."""
    try:
        response = db.get_all_tasks()
        data = handle_response(response)
        is_admin = current_user.get("role") == "admin"
        if isinstance(data, list):
            for task in data:
                # Security: Strip edited_by if not admin
                if not is_admin:
                    task.pop("edited_by", None)
                # RBAC: Strip restricted financial data for ManagerAdmin
                if current_user.get("access_level") == "ManagerAdmin":
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
        data = handle_response(response)
        if current_user.get("role") != "admin" and isinstance(data, dict):
            data.pop("edited_by", None)
        return data
    except HTTPException:
        raise
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
        is_admin = current_user.get("role") == "admin"
        if isinstance(data, list):
            for task in data:
                # Security: Strip edited_by if not admin
                if not is_admin:
                    task.pop("edited_by", None)
                # RBAC: Strip restricted financial data for ManagerAdmin
                if current_user.get("access_level") == "ManagerAdmin":
                    task.pop("employee_cost", None)
                    task.pop("billing_amount", None)
                    task.pop("profit_loss", None)
        return data
    except Exception as e:
        logger.error(f"Router Error in get_tasks_by_employee: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve employee task history.")

# ==========================================
#          TIMESHEET EDIT ENDPOINTS
# ==========================================

from datetime import datetime

def _parse_created_at(dt_str):
    if not dt_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None

@router.put("/developer/update/{task_id}", tags=["Timesheets & Tasks"])
def update_developer_task(task_id: str, task_update: DeveloperTaskUpdate, current_user: dict = Depends(get_current_user)):
    try:
        # 1. Fetch the existing task to verify ownership and timing
        response = db.get_task(task_id)
        existing_task = handle_response(response)
        if not existing_task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # 2. Check permissions
        if current_user.get("role") != "admin":
            # Must own the task
            if existing_task.get("employee_id") != current_user.get("id"):
                raise HTTPException(status_code=403, detail="You do not have permission to edit this timesheet entry.")
            
            # Check 24-hour limit from creation time
            created_at_str = existing_task.get("created_at")
            if not created_at_str:
                raise HTTPException(status_code=400, detail="Task missing log creation timestamp.")
            
            created_at = _parse_created_at(created_at_str)
            if not created_at:
                raise HTTPException(status_code=400, detail="Invalid creation timestamp format. Cannot edit.")
            
            time_elapsed = datetime.now() - created_at
            if time_elapsed.total_seconds() > 24 * 3600:
                raise HTTPException(status_code=403, detail="Timesheet entry cannot be edited after 24 hours.")
        
        # 3. Prepare data for update
        data = task_update.model_dump(exclude_unset=True)
        data["is_edited"] = True
        data["edited_by"] = current_user.get("username")
        
        # 4. Call database update
        response = db.edit_developer_task(task_id, data)
        resp_dict = json.loads(response)
        if "error" in resp_dict:
            raise HTTPException(status_code=400, detail=resp_dict["error"])
        
        # Strip edited_by if updating user is not admin
        if current_user.get("role") != "admin":
            resp_dict.pop("edited_by", None)
            
        return resp_dict
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in update_developer_task: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update developer timesheet.")

@router.put("/content/update/{task_id}", tags=["Timesheets & Tasks"])
def update_content_task(task_id: str, task_update: ContentTaskUpdate, current_user: dict = Depends(get_current_user)):
    try:
        # 1. Fetch the existing task to verify ownership and timing
        response = db.get_task(task_id)
        existing_task = handle_response(response)
        if not existing_task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # 2. Check permissions
        if current_user.get("role") != "admin":
            # Must own the task
            if existing_task.get("employee_id") != current_user.get("id"):
                raise HTTPException(status_code=403, detail="You do not have permission to edit this timesheet entry.")
            
            # Check 24-hour limit from creation time
            created_at_str = existing_task.get("created_at")
            if not created_at_str:
                raise HTTPException(status_code=400, detail="Task missing log creation timestamp.")
            
            created_at = _parse_created_at(created_at_str)
            if not created_at:
                raise HTTPException(status_code=400, detail="Invalid creation timestamp format. Cannot edit.")
            
            time_elapsed = datetime.now() - created_at
            if time_elapsed.total_seconds() > 24 * 3600:
                raise HTTPException(status_code=403, detail="Timesheet entry cannot be edited after 24 hours.")
        
        # 3. Prepare data for update
        data = task_update.model_dump(exclude_unset=True)
        data["is_edited"] = True
        data["edited_by"] = current_user.get("username")
        
        # 4. Call database update
        response = db.edit_content_creator_task(task_id, data)
        resp_dict = json.loads(response)
        if "error" in resp_dict:
            raise HTTPException(status_code=400, detail=resp_dict["error"])
        
        # Strip edited_by if updating user is not admin
        if current_user.get("role") != "admin":
            resp_dict.pop("edited_by", None)
            
        return resp_dict
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in update_content_task: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update content creator timesheet.")