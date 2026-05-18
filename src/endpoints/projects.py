from fastapi import APIRouter, Depends, HTTPException
import logging
from schemas import (
    ProjectCreate, ProjectUpdate,
    TimelineCreate, TimelineUpdate,
    SRSCreate, SRSUpdate, ProjectAssignmentCreate, ManagerCreate, ProjectExpenseCreate,
    MilestoneAssignmentCreate, ProjectPaymentCreate, ProjectPaymentUpdate
)
from src.database.database_operations import DatabaseOperations
from src.endpoints.auth import get_current_user, handle_response

logger = logging.getLogger("Yana_Projects_Router")
router = APIRouter(prefix="/projects", tags=["Project Management"])
db = DatabaseOperations()

# ==========================================
#              MANAGERS
# ==========================================

@router.post("/managers/create", tags=["Project Management"])
def create_manager(manager: ManagerCreate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can add managers.")
    try:
        data = manager.model_dump(exclude_unset=True)
        response = db.add_manager(data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in create_manager: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add new manager.")

@router.get("/managers/all", tags=["Project Management"])
def get_all_managers(current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_all_managers()
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_all_managers: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch managers.")

# ==========================================
#              CORE PROJECTS
# ==========================================

@router.post("/create", tags=["Project Management"])
def create_project(project: ProjectCreate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can register projects.")
    try:
        data = project.model_dump(exclude_unset=True)
        response = db.add_project(data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in create_project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to initialize new project.")

@router.get("/all", tags=["Project Management"])
def get_all_projects(current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_all_projects()
        data = handle_response(response)
        if current_user.get("access_level") == "ManagerAdmin" and isinstance(data, list):
            for proj in data:
                if isinstance(proj, dict):
                    proj.pop("client_cost", None)
                    proj.pop("approx_cost", None)
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_all_projects: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch active projects.")

@router.get("/get/{project_id}", tags=["Project Management"])
def get_project(project_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_project(project_id)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve project scope.")

@router.put("/update/{project_id}", tags=["Project Management"])
def update_project(project_id: str, project: ProjectUpdate, current_user: dict = Depends(get_current_user)):
    try:
        data = project.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No valid data provided to update.")
        response = db.edit_project(project_id, data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in update_project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update project data.")

@router.delete("/delete/{project_id}", tags=["Project Management"])
def delete_project(project_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Critical Action Denied: Admin authorization required.")
    try:
        response = db.delete_project(project_id)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in delete_project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete project.")


# ==========================================
#          PROJECT TIMELINES
# ==========================================

@router.get("/timeline/{project_id}", tags=["Project Management"])
def get_project_timeline(project_id: str, current_user: dict = Depends(get_current_user)):
    try:
        employee_id = current_user.get("id") if current_user.get("role") != "admin" else None
        response = db.get_project_timeline(project_id, employee_id=employee_id)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_project_timeline: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch timeline milestones.")

@router.post("/timeline/create", tags=["Project Management"])
def create_project_timeline(timeline: TimelineCreate, current_user: dict = Depends(get_current_user)):
    try:
        data = timeline.model_dump(exclude_unset=True)
        response = db.add_project_timeline(data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in create_project_timeline: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add timeline milestone.")

@router.put("/timeline/update/{timeline_id}", tags=["Project Management"])
def update_project_timeline(timeline_id: str, timeline: TimelineUpdate, current_user: dict = Depends(get_current_user)):
    try:
        data = timeline.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No data provided to update.")
        response = db.edit_project_timeline(timeline_id, data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in update_project_timeline: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update timeline milestone.")

@router.delete("/timeline/delete/{timeline_id}", tags=["Project Management"])
def delete_project_timeline(timeline_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.delete_project_timeline(timeline_id)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in delete_project_timeline: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete timeline milestone.")

@router.post("/timeline/assign", tags=["Project Management"])
def assign_employee_to_milestone(assignment: MilestoneAssignmentCreate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can assign employees to milestones.")
    try:
        data = assignment.model_dump(exclude_unset=True)
        response = db.assign_employee_to_milestone(data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in assign_employee_to_milestone: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to assign employee to milestone.")

@router.get("/timeline/assignments/{milestone_id}", tags=["Project Management"])
def get_milestone_assignments(milestone_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_milestone_assignments(milestone_id)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_milestone_assignments: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch milestone assignments.")

@router.delete("/timeline/unassign/{assignment_id}", tags=["Project Management"])
def unassign_employee_from_milestone(assignment_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Critical Action Denied: Admin authorization required.")
    try:
        response = db.unassign_employee_from_milestone(assignment_id)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in unassign_employee_from_milestone: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to unassign employee from milestone.")


# ==========================================
#             SRS DOCUMENTS
# ==========================================

@router.get("/srs/get_by_project/{project_id}", tags=["Project Management"])
def get_project_srs(project_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_srs_by_project(project_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_project_srs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch SRS documents.")

@router.post("/srs/create", tags=["Project Management"])
def create_srs_document(srs: SRSCreate, current_user: dict = Depends(get_current_user)):
    try:
        data = srs.model_dump(exclude_unset=True)
        # Note: If you want to auto-assign the 'approved_by', you can link current_user.get("username") here.
        response = db.add_srs_document(data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in create_srs_document: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to link SRS document to project.")

@router.put("/srs/update/{srs_id}", tags=["Project Management"])
def update_srs_document(srs_id: str, srs: SRSUpdate, current_user: dict = Depends(get_current_user)):
    try:
        data = srs.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No data provided to update.")
        response = db.edit_srs_document(srs_id, data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in update_srs_document: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update SRS document properties.")

@router.delete("/srs/delete/{srs_id}", tags=["Project Management"])
def delete_srs_document(srs_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.delete_srs_document(srs_id)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in delete_srs_document: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to remove SRS document from the system.")

# ==========================================
#          PROJECT ASSIGNMENTS (PHASE 5)
# ==========================================

@router.post("/assign", tags=["Project Management"])
def assign_employee_to_project(assignment: ProjectAssignmentCreate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can manage project assignments.")
    try:
        data = assignment.model_dump(exclude_unset=True)
        response = db.assign_employee_to_project(data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in assign_employee_to_project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to assign employee to project.")

@router.get("/assignments/{project_id}", tags=["Project Management"])
def get_project_assignments(project_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_project_assignments(project_id)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_project_assignments: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch project assignments.")

@router.get("/employee/{employee_id}", tags=["Project Management"])
def get_employee_projects(employee_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_employee_projects(employee_id)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_employee_projects: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch employee's assigned projects.")

@router.delete("/unassign/{assignment_id}", tags=["Project Management"])
def unassign_employee(assignment_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Critical Action Denied: Admin authorization required.")
    try:
        response = db.unassign_employee(assignment_id)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in unassign_employee: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to remove assignment.")

# ==========================================
#             PROJECT EXPENSES
# ==========================================

@router.post("/expenses/create", tags=["Project Management"])
def create_project_expense(expense: ProjectExpenseCreate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can add expenses.")
    try:
        data = expense.model_dump(exclude_unset=True)
        response = db.add_project_expense(data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in create_project_expense: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add project expense.")

@router.get("/expenses/{project_id}", tags=["Project Management"])
def get_project_expenses(project_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_project_expenses(project_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_project_expenses: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch project expenses.")

@router.delete("/expenses/delete/{expense_id}", tags=["Project Management"])
def delete_project_expense(expense_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can delete expenses.")
    try:
        response = db.delete_project_expense(expense_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in delete_project_expense: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete expense.")

# ==========================================
#          PROJECT PAYMENTS
# ==========================================

@router.post("/payments/create", tags=["Project Management"])
def create_project_payment(payment: ProjectPaymentCreate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can log payments.")
    try:
        data = payment.model_dump(exclude_unset=True)
        response = db.add_project_payment(data)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in create_project_payment: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to log payment.")

@router.get("/payments/{project_id}", tags=["Project Management"])
def get_project_payments(project_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_project_payments(project_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_project_payments: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch payments.")

@router.delete("/payments/delete/{payment_id}", tags=["Project Management"])
def delete_project_payment(payment_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can delete payments.")
    try:
        response = db.delete_project_payment(payment_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in delete_project_payment: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete payment.")