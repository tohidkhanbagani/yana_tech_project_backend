from fastapi import APIRouter, Depends, HTTPException, Response
import logging
from schemas import (
    ProjectCreate, ProjectUpdate,
    TimelineCreate, TimelineUpdate,
    SRSCreate, SRSUpdate, ProjectAssignmentCreate, ProjectAssignmentUpdate, ProjectExpenseCreate, ProjectExpenseUpdate,
    MilestoneAssignmentCreate, ProjectPaymentCreate, ProjectPaymentUpdate,
    ClientReceivableCreate, ClientReceivableUpdate
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
        
        # Auto-assign the manager if they have an employee profile
        try:
            import json
            resp_data = json.loads(response)
            proj_id = resp_data.get("id")
            mgr_username = resp_data.get("manager")
            if proj_id and mgr_username and mgr_username != "N/A":
                from src.database.database_create import SessionLocal
                from src.database.database_tables import Employees, ProjectAssignments
                with SessionLocal() as session:
                    emp = session.query(Employees).filter(Employees.username == mgr_username).first()
                    if emp:
                        existing = session.query(ProjectAssignments).filter_by(project_id=proj_id, employee_id=emp.id).first()
                        if not existing:
                            new_assign = ProjectAssignments(
                                project_id=proj_id,
                                employee_id=emp.id,
                                custom_hourly_cost=emp.hourly_cost_rate,
                                custom_hourly_billing=emp.hourly_billing_rate
                            )
                            session.add(new_assign)
                            session.commit()
        except Exception as assign_err:
            logger.error(f"Auto assignment of manager failed in create_project: {str(assign_err)}")
        
        try:
            user_id = current_user.get("username", "Unknown")
            # Parse response if it is a JSON string
            import json
            resp_obj = json.loads(response) if isinstance(response, str) else response
            proj_id = resp_obj.get("id") if isinstance(resp_obj, dict) else None
            db.write_audit_log(
                user_id=user_id,
                action="PROJECT_CREATE",
                target_id=str(proj_id) if proj_id else None,
                details={
                    "project_name": data.get("name"),
                    "cost_type": data.get("cost_type"),
                    "client_cost": data.get("client_cost"),
                    "budget": data.get("budget"),
                    "manager": data.get("manager")
                }
            )
        except Exception as audit_err:
            logger.error(f"Audit log failed in create_project: {str(audit_err)}")

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
            from src.database.database_create import SessionLocal
            from src.database.database_tables import Employees, ProjectAssignments
            with SessionLocal() as session:
                employee = session.query(Employees).filter(Employees.username == current_user.get("username")).first()
                if employee:
                    assignments = session.query(ProjectAssignments).filter(ProjectAssignments.employee_id == employee.id).all()
                    assigned_project_ids = {a.project_id for a in assignments}
                else:
                    assigned_project_ids = set()
            
            data = [proj for proj in data if isinstance(proj, dict) and (proj.get("id") in assigned_project_ids or proj.get("manager") == current_user.get("username"))]
            for proj in data:
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
    if current_user.get("access_level") == "ManagerAdmin":
        from src.database.database_create import SessionLocal
        from src.database.database_tables import Employees, ProjectAssignments, Projects
        with SessionLocal() as session:
            employee = session.query(Employees).filter(Employees.username == current_user.get("username")).first()
            if not employee:
                raise HTTPException(status_code=403, detail="Access denied. No employee profile for manager.")
            assigned = session.query(ProjectAssignments).filter(
                ProjectAssignments.project_id == project_id,
                ProjectAssignments.employee_id == employee.id
            ).first()
            project_obj = session.query(Projects).filter(Projects.id == project_id).first()
            is_manager = project_obj and project_obj.manager == current_user.get("username")
            if not assigned and not is_manager:
                raise HTTPException(status_code=403, detail="Access denied. You are not assigned to this project.")
    try:
        response = db.get_project(project_id)
        data = handle_response(response)
        if current_user.get("access_level") == "ManagerAdmin" and isinstance(data, dict):
            data.pop("client_cost", None)
            data.pop("approx_cost", None)
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve project scope.")

@router.get("/details/aggregated/{project_id}", tags=["Project Management"])
def get_aggregated_project(project_id: str, current_user: dict = Depends(get_current_user)):
    # 1. Access Control: Block employees (they don't use Command Center)
    if current_user.get("role") != "admin" and current_user.get("access_level") != "ManagerAdmin":
        raise HTTPException(status_code=403, detail="Unauthorized access to aggregated project details.")
    
    # 2. Manager validation (verify assignment or project manager)
    if current_user.get("access_level") == "ManagerAdmin":
        from src.database.database_create import SessionLocal
        from src.database.database_tables import Employees, ProjectAssignments, Projects
        with SessionLocal() as session:
            employee = session.query(Employees).filter(Employees.username == current_user.get("username")).first()
            if not employee:
                raise HTTPException(status_code=403, detail="Access denied. No employee profile for manager.")
            assigned = session.query(ProjectAssignments).filter(
                ProjectAssignments.project_id == project_id,
                ProjectAssignments.employee_id == employee.id
            ).first()
            project_obj = session.query(Projects).filter(Projects.id == project_id).first()
            is_manager = project_obj and project_obj.manager == current_user.get("username")
            if not assigned and not is_manager:
                raise HTTPException(status_code=403, detail="Access denied. You are not assigned to this project.")

    try:
        # Fetch timeline filtered for manager if applicable, else return full timeline for admin
        employee_id = current_user.get("id") if current_user.get("role") != "admin" else None
        
        response = db.get_aggregated_project_details(project_id, employee_id=employee_id)
        data = handle_response(response)
        
        if isinstance(data, dict):
            # 3. RBAC Stripping for ManagerAdmin
            if current_user.get("access_level") == "ManagerAdmin":
                # Strip sensitive fields from project
                proj = data.get("project")
                if isinstance(proj, dict):
                    proj.pop("client_cost", None)
                    proj.pop("approx_cost", None)
                
                # Strip sensitive fields from tasks
                tasks = data.get("tasks")
                if isinstance(tasks, list):
                    for task in tasks:
                        if isinstance(task, dict):
                            task.pop("employee_cost", None)
                            task.pop("billing_amount", None)
                            task.pop("profit_loss", None)
                
                # Managers do not view payments/receivables
                data["payments"] = []
                data["receivables"] = []
                
            # 4. Standard security: strip edited_by from tasks if not admin
            if current_user.get("role") != "admin":
                tasks = data.get("tasks")
                if isinstance(tasks, list):
                    for task in tasks:
                        if isinstance(task, dict):
                            task.pop("edited_by", None)
                            
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_aggregated_project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve aggregated project scope.")

@router.put("/update/{project_id}", tags=["Project Management"])
def update_project(project_id: str, project: ProjectUpdate, current_user: dict = Depends(get_current_user)):
    try:
        data = project.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No valid data provided to update.")
        response = db.edit_project(project_id, data)
        
        try:
            user_id = current_user.get("username", "Unknown")
            db.write_audit_log(
                user_id=user_id,
                action="PROJECT_UPDATE",
                target_id=str(project_id),
                details=data
            )
        except Exception as audit_err:
            logger.error(f"Audit log failed in update_project: {str(audit_err)}")

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
        
        try:
            user_id = current_user.get("username", "Unknown")
            db.write_audit_log(
                user_id=user_id,
                action="PROJECT_DELETE",
                target_id=str(project_id),
                details={"status": "deleted"}
            )
        except Exception as audit_err:
            logger.error(f"Audit log failed in delete_project: {str(audit_err)}")

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
def get_project_timeline(project_id: str, employee_id: str = None, current_user: dict = Depends(get_current_user)):
    try:
        if current_user.get("role") != "admin" and not employee_id:
            employee_id = current_user.get("id")
        response = db.get_project_timeline(project_id, employee_id=employee_id)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_project_timeline: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch timeline milestones.")

@router.get("/timeline/employee/{employee_id}", tags=["Project Management"])
def get_employee_milestones(employee_id: str, current_user: dict = Depends(get_current_user)):
    try:
        if current_user.get("role") == "employee" and current_user.get("id") != employee_id:
            raise HTTPException(status_code=403, detail="Unauthorized access to milestones.")
        response = db.get_employee_assigned_milestones(employee_id)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_employee_milestones: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch employee milestones.")

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
    if current_user.get("role") not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Only administrators and managers can manage SRS documents.")
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
    if current_user.get("role") not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Only administrators and managers can manage SRS documents.")
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
    if current_user.get("role") not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Only administrators and managers can manage SRS documents.")
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
    if current_user.get("role") not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Only administrators and managers can manage project assignments.")
    try:
        data = assignment.model_dump(exclude_unset=True)
        response = db.assign_employee_to_project(data)
        
        try:
            user_id = current_user.get("username", "Unknown")
            db.write_audit_log(
                user_id=user_id,
                action="EMPLOYEE_ASSIGN",
                target_id=str(data.get("project_id")),
                details={
                    "employee_id": data.get("employee_id"),
                    "custom_hourly_cost": data.get("custom_hourly_cost"),
                    "custom_hourly_billing": data.get("custom_hourly_billing")
                }
            )
        except Exception as audit_err:
            logger.error(f"Audit log failed in assign_employee_to_project: {str(audit_err)}")

        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in assign_employee_to_project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to assign employee to project.")

@router.get("/assignments/all", tags=["Project Management"])
def get_all_project_assignments(current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_all_project_assignments()
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_all_project_assignments: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch all project assignments mapping.")

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
    if current_user.get("role") not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Critical Action Denied: Admin or Manager authorization required.")
    try:
        response = db.unassign_employee(assignment_id)
        
        try:
            user_id = current_user.get("username", "Unknown")
            db.write_audit_log(
                user_id=user_id,
                action="EMPLOYEE_REMOVE",
                target_id=str(assignment_id),
                details={"status": "unassigned"}
            )
        except Exception as audit_err:
            logger.error(f"Audit log failed in unassign_employee: {str(audit_err)}")

        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in unassign_employee: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to remove assignment.")

@router.put("/assignments/update/{assignment_id}", tags=["Project Management"])
def update_project_assignment(assignment_id: str, assignment: ProjectAssignmentUpdate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Only administrators and managers can modify assignments.")
    try:
        data = assignment.model_dump(exclude_unset=True)
        response = db.edit_project_assignment(assignment_id, data)
        
        try:
            user_id = current_user.get("username", "Unknown")
            db.write_audit_log(
                user_id=user_id,
                action="ASSIGNMENT_RATE_UPDATE",
                target_id=str(assignment_id),
                details=data
            )
        except Exception as audit_err:
            logger.error(f"Audit log failed in update_project_assignment: {str(audit_err)}")

        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in update_project_assignment: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update project assignment.")

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

@router.put("/expenses/update/{expense_id}", tags=["Project Management"])
def update_project_expense(expense_id: str, expense: ProjectExpenseUpdate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin" or current_user.get("access_level") != "SystemAdmin":
        raise HTTPException(status_code=403, detail="Only System Administrators have authorization to edit project expenses.")
    try:
        data = expense.model_dump(exclude_unset=True)
        response = db.edit_project_expense(expense_id, data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in update_project_expense: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update project expense.")

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

@router.get("/export/{project_id}", tags=["Project Management"])
def export_project_xlsx(project_id: str, current_user: dict = Depends(get_current_user)):
    try:
        xlsx_data = db.export_project_xlsx_data(project_id)
        if xlsx_data is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        
        # If there's an error encoded in a JSON string returned by DatabaseOperations
        # (e.g. {"error": "..."} or {"critical_error": "..."})
        if isinstance(xlsx_data, bytes):
            try:
                decoded_str = xlsx_data.decode('utf-8', errors='ignore').strip()
                if decoded_str.startswith('{"'):
                    import json
                    err = json.loads(decoded_str)
                    if "error" in err or "critical_error" in err:
                        raise HTTPException(status_code=400, detail=err.get("error") or err.get("critical_error"))
            except Exception:
                pass
        elif isinstance(xlsx_data, str) and xlsx_data.strip().startswith('{"'):
            try:
                import json
                err = json.loads(xlsx_data)
                if "error" in err or "critical_error" in err:
                    raise HTTPException(status_code=400, detail=err.get("error") or err.get("critical_error"))
            except ValueError:
                pass

        # Fetch project name for the filename
        proj_response = db.get_project(project_id)
        import json
        proj_name = "project"
        try:
            proj_info = json.loads(proj_response)
            if isinstance(proj_info, dict) and "name" in proj_info:
                proj_name = proj_info["name"]
        except Exception:
            pass

        # Format clean filename
        import re
        clean_name = re.sub(r'[^a-zA-Z0-9]+', '_', proj_name).lower()
        filename = f"project_{clean_name}_export.xlsx"

        return Response(
            content=xlsx_data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in export_project_xlsx: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to export project data Excel.")


# ==========================================
#          CLIENT RECEIVABLES / REMINDERS
# ==========================================

@router.post("/receivables/create", tags=["Project Management"])
def create_client_receivable(receivable: ClientReceivableCreate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can manage client receivables.")
    try:
        data = receivable.model_dump(exclude_unset=True)
        response = db.add_client_receivable(data)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in create_client_receivable: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add client receivable.")

@router.get("/receivables/{project_id}", tags=["Project Management"])
def get_client_receivables(project_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_client_receivables(project_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_client_receivables: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch client receivables.")

@router.delete("/receivables/delete/{receivable_id}", tags=["Project Management"])
def delete_client_receivable(receivable_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can manage client receivables.")
    try:
        response = db.delete_client_receivable(receivable_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in delete_client_receivable: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete client receivable.")

@router.put("/receivables/mark-done/{receivable_id}", tags=["Project Management"])
def mark_client_receivable_done(receivable_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.mark_client_receivable_done(receivable_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in mark_client_receivable_done: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to mark receivable as done.")

@router.get("/receivables/pending", tags=["Project Management"])
def get_pending_client_receivables(current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_all_pending_client_receivables(user_id=current_user.get("id"))
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_pending_client_receivables: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch pending client receivables.")
