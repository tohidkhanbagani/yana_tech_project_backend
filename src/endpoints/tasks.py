from fastapi import APIRouter, Depends, HTTPException
import logging
from typing import List, Optional
from datetime import datetime, timedelta
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

def _parse_created_at(date_str):
    if not date_str: return None
    try:
        if "T" in date_str:
            return datetime.fromisoformat(date_str.replace("Z", ""))
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return None

@router.get("/all", tags=["Timesheets & Tasks"])
def get_all_tasks(start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Fetches ALL tasks. Defaults to last 2 days for performance if no dates provided."""
    try:
        response = db.get_all_tasks()
        data = handle_response(response)
        
        # Apply date filtering
        if isinstance(data, list):
            now = datetime.now()
            # Default to last 2 days and include today fully
            s_dt = now - timedelta(days=2)
            e_dt = now + timedelta(days=1)
            
            if start_date:
                try:
                    s_dt = datetime.fromisoformat(start_date.replace("Z", ""))
                except:
                    s_dt = datetime.strptime(start_date, "%Y-%m-%d")
            if end_date:
                try:
                    e_dt = datetime.fromisoformat(end_date.replace("Z", ""))
                    # Move to end of the day if it's just a date
                    if len(end_date) <= 10:
                        e_dt = e_dt + timedelta(days=1)
                except:
                    e_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

            filtered_data = []
            for t in data:
                created = _parse_created_at(t.get("created_at") or t.get("date"))
                if created and s_dt <= created <= e_dt:
                    filtered_data.append(t)
            data = filtered_data

            if current_user.get("access_level") == "ManagerAdmin":
                from src.database.database_create import SessionLocal
                from src.database.database_tables import Employees, ProjectAssignments
                with SessionLocal() as session:
                    employee = session.query(Employees).filter(Employees.username == current_user.get("username")).first()
                    if employee:
                        assignments = session.query(ProjectAssignments).filter(ProjectAssignments.employee_id == employee.id).all()
                        assigned_project_ids = {a.project_id for a in assignments}
                    else:
                        assigned_project_ids = set()
                data = [t for t in data if t.get("project_id") in assigned_project_ids]

            is_admin = current_user.get("role") == "admin"
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
        if isinstance(data, dict):
            if current_user.get("access_level") == "ManagerAdmin":
                from src.database.database_create import SessionLocal
                from src.database.database_tables import Employees, ProjectAssignments
                with SessionLocal() as session:
                    employee = session.query(Employees).filter(Employees.username == current_user.get("username")).first()
                    if not employee:
                        raise HTTPException(status_code=403, detail="Access denied. No employee profile for manager.")
                    assigned = session.query(ProjectAssignments).filter(
                        ProjectAssignments.project_id == data.get("project_id"),
                        ProjectAssignments.employee_id == employee.id
                    ).first()
                    if not assigned:
                        raise HTTPException(status_code=403, detail="Access denied. You are not assigned to this project.")
            if current_user.get("role") != "admin":
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
        
        if current_user.get("access_level") == "ManagerAdmin" and isinstance(data, list):
            from src.database.database_create import SessionLocal
            from src.database.database_tables import Employees, ProjectAssignments
            with SessionLocal() as session:
                employee = session.query(Employees).filter(Employees.username == current_user.get("username")).first()
                if employee:
                    assignments = session.query(ProjectAssignments).filter(ProjectAssignments.employee_id == employee.id).all()
                    assigned_project_ids = {a.project_id for a in assignments}
                else:
                    assigned_project_ids = set()
            data = [t for t in data if t.get("project_id") in assigned_project_ids]

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

@router.get("/get_by_project/{project_id}", tags=["Timesheets & Tasks"])
def get_tasks_by_project(project_id: str, current_user: dict = Depends(get_current_user)):
    """Fetches all tasks linked to a specific project."""
    if current_user.get("access_level") == "ManagerAdmin":
        from src.database.database_create import SessionLocal
        from src.database.database_tables import Employees, ProjectAssignments
        with SessionLocal() as session:
            employee = session.query(Employees).filter(Employees.username == current_user.get("username")).first()
            if not employee:
                raise HTTPException(status_code=403, detail="Access denied. No employee profile for manager.")
            assigned = session.query(ProjectAssignments).filter(
                ProjectAssignments.project_id == project_id,
                ProjectAssignments.employee_id == employee.id
            ).first()
            if not assigned:
                raise HTTPException(status_code=403, detail="Access denied. You are not assigned to this project.")
    try:
        response = db.get_all_tasks()
        data = handle_response(response)
        if isinstance(data, list):
            data = [t for t in data if str(t.get("project_id")) == str(project_id)]
            is_admin = current_user.get("role") == "admin"
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
        logger.error(f"Router Error in get_tasks_by_project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve project task history.")


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
        
        # Validation of project assignments & milestones
        if "project_id" in data:
            new_project_id = data["project_id"]
            if not new_project_id:
                data["project_id"] = None
                data["milestone_id"] = None
            else:
                target_employee_id = existing_task.get("employee_id")
                response_assign = db.get_project_assignments(new_project_id)
                assignments = handle_response(response_assign)
                assigned_employee_ids = [a.get("employee_id") for a in assignments] if isinstance(assignments, list) else []
                if target_employee_id not in assigned_employee_ids:
                    raise HTTPException(status_code=403, detail="Employee is not assigned to the selected project.")
                    
        new_milestone_id = data.get("milestone_id")
        if new_milestone_id:
            check_project_id = data.get("project_id") or existing_task.get("project_id")
            if not check_project_id:
                raise HTTPException(status_code=400, detail="Cannot assign a milestone without a project.")
            response_milestones = db.get_project_timeline(check_project_id)
            milestones = handle_response(response_milestones)
            milestone_ids = [m.get("id") for m in milestones] if isinstance(milestones, list) else []
            if new_milestone_id not in milestone_ids:
                raise HTTPException(status_code=400, detail="Selected milestone does not belong to the project.")

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
        
        # Validation of project assignments
        if "project_id" in data:
            new_project_id = data["project_id"]
            if not new_project_id:
                data["project_id"] = None
                data["milestone_id"] = None
            else:
                target_employee_id = existing_task.get("employee_id")
                response_assign = db.get_project_assignments(new_project_id)
                assignments = handle_response(response_assign)
                assigned_employee_ids = [a.get("employee_id") for a in assignments] if isinstance(assignments, list) else []
                if target_employee_id not in assigned_employee_ids:
                    raise HTTPException(status_code=403, detail="Employee is not assigned to the selected project.")

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

@router.get("/handover/pending", tags=["Timesheets & Tasks"])
def get_pending_handover_tasks(assignee_id: str, colleague_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_pending_handover_tasks(assignee_id, colleague_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_pending_handover_tasks: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve pending handover tasks.")
