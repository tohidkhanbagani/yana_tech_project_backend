from fastapi import APIRouter, Depends, HTTPException
import logging
from schemas import (
    ProjectCreate, ProjectUpdate,
    TimelineCreate, TimelineUpdate,
    SRSCreate, SRSUpdate, ProjectAssignmentCreate
)
from src.database.database_operations import DatabaseOperations
from src.endpoints.auth import get_current_user, handle_response

logger = logging.getLogger("Yana_Projects_Router")
router = APIRouter(prefix="/projects", tags=["Project Management"])
db = DatabaseOperations()

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
        return handle_response(response)
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
        response = db.get_project_timeline(project_id)
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