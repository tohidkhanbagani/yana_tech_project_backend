import uuid as _uuid
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError, NoResultFound
from sqlalchemy.inspection import inspect
from passlib.context import CryptContext

from .database_create import SessionLocal
from .database_tables import (
    Departments_Roles, Admins, Employees, LoginHistory,
    Projects, SRS_Documents, ProjectTimeline, ProjectAssignments,
    DeveloperTasks, ContentCreatorTasks
)
# ==========================================
#              LOGGING SETUP
# ==========================================
# Professional logging setup for granular debugging.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger("YanaDB_Operations")

# Setup password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

class DatabaseOperations:

    def __init__(self):
        # We use the factory directly so we can generate isolated sessions per request
        self.SessionLocal = SessionLocal

    # ==========================================
    #             UTILITY METHODS
    # ==========================================

    def model_to_dict(self, obj) -> dict:
        """Safely converts a SQLAlchemy model instance to a Python dictionary."""
        if not obj:
            return {}
        return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs}

    def _handle_error(self, operation: str, exception: Exception, context: dict = None) -> str:
        """
        Centralized, professional error handler. 
        Logs the full stack trace securely on the server, while returning a safe JSON structure to the client.
        """
        context_str = json.dumps(context, default=str) if context else "No context provided"
        logger.error(f"DB_ERROR in '{operation}' | Context: {context_str} | Err: {str(exception)}", exc_info=True)
        
        if isinstance(exception, IntegrityError):
            return json.dumps({
                "error": "Database integrity violation. A required link (foreign key) is missing, or a unique constraint (like an existing username) was violated.",
                "details": str(exception.orig)
            })
        elif isinstance(exception, SQLAlchemyError):
            return json.dumps({
                "critical_error": "A deep database transaction error occurred.",
                "details": str(exception)
            })
        else:
            return json.dumps({
                "critical_error": "An unexpected application error occurred.",
                "details": str(exception)
            })

    # ==========================================
    #        DEPARTMENTS & ROLES (PHASE 2)
    # ==========================================

    def add_department_role(self, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                dept_role = Departments_Roles(**data)
                session.add(dept_role)
                session.commit()
                session.refresh(dept_role)
                logger.info(f"Created new Department/Role: {dept_role.department_name} - {dept_role.role_name}")
                return json.dumps(self.model_to_dict(dept_role), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("add_department_role", e, context=data)

    def get_all_departments_roles(self) -> str:
        with self.SessionLocal() as session:
            try:
                roles = session.query(Departments_Roles).all()
                return json.dumps([self.model_to_dict(r) for r in roles], indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_all_departments_roles", e)

    # ==========================================
    #        ADMINS & EMPLOYEES (PHASE 2)
    # ==========================================

    def add_admin(self, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                if 'password' in data:
                    data['password'] = get_password_hash(data['password'])
                
                new_admin = Admins(**data)
                session.add(new_admin)
                session.commit()
                session.refresh(new_admin)
                
                # Strip password from return dict for security
                res_dict = self.model_to_dict(new_admin)
                res_dict.pop('password', None)
                
                logger.info(f"Created new Admin: {new_admin.username}")
                return json.dumps(res_dict, indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("add_admin", e, context={"username": data.get("username")})

    def add_employee(self, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                # 1. Username Auto-Generation Logic (if missing)
                full_name = data.get("full_name", "employee").strip()
                if not full_name or full_name.lower() == "undefined":
                    full_name = "employee"

                if not data.get("username"):
                    base_username = full_name.lower().replace(" ", ".")
                    username = base_username
                    counter = 1
                    # Check for uniqueness across Employees AND Admins
                    while session.query(Employees).filter_by(username=username).first() or \
                          session.query(Admins).filter_by(username=username).first():
                        username = f"{base_username}{counter}"
                        counter += 1
                    data["username"] = username

                # 2. Password Handling
                default_password = data.get("password") or "YanaUser123!"
                data["password"] = get_password_hash(default_password)

                # 3. Insert Database Record
                new_employee = Employees(**data)
                session.add(new_employee)
                session.commit()
                session.refresh(new_employee)
                
                res_dict = self.model_to_dict(new_employee)
                res_dict['generated_password'] = default_password # Return plain text ONCE for the admin to copy
                
                logger.info(f"Created new Employee: {new_employee.username}")
                return json.dumps(res_dict, indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("add_employee", e, context={"full_name": data.get("full_name")})

    def get_all_employees(self) -> str:
        with self.SessionLocal() as session:
            try:
                employees = session.query(Employees).all()
                results = []
                for emp in employees:
                    emp_dict = self.model_to_dict(emp)
                    emp_dict.pop('password', None)
                    results.append(emp_dict)
                return json.dumps(results, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_all_employees", e)

    def edit_employee(self, employee_id: str, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                employee = session.query(Employees).filter_by(id=employee_id).first()
                if not employee:
                    return json.dumps({"error": f"Employee {employee_id} not found."})
                
                for key, value in data.items():
                    if key == "password":
                        value = get_password_hash(value)
                    setattr(employee, key, value)
                
                session.commit()
                session.refresh(employee)
                res = self.model_to_dict(employee)
                res.pop('password', None)
                return json.dumps(res, indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("edit_employee", e, context={"employee_id": employee_id})

    # ==========================================
    #     TASK INTERCEPTORS & CALCULATIONS
    # ==========================================

    def add_developer_task(self, data: dict) -> str:
        """
        Calculation Engine Trigger: Intercepts developer timesheet, auto-calculates 
        costs and profits based on Employee's preset hourly rates.
        """
        with self.SessionLocal() as session:
            try:
                employee_id = data.get("employee_id")
                if not employee_id:
                    return json.dumps({"error": "employee_id is required for Developer Tasks."})
                
                # --- PHASE 5: ADVANCED FINANCIAL AUTO-CALCULATION ---
                employee = session.query(Employees).filter_by(id=employee_id).first()
                if not employee:
                    return json.dumps({"error": f"Employee {employee_id} not found. Cannot calculate costs."})
                    
                project_id = data.get("project_id")
                cost_rate = float(employee.hourly_cost_rate or 0.0)
                billing_rate = float(employee.hourly_billing_rate or 0.0)

                # Intercept logic: If working on a specific project, check for custom whitelist rates
                if project_id:
                    assignment = session.query(ProjectAssignments).filter_by(
                        project_id=project_id, 
                        employee_id=employee_id
                    ).first()
                    
                    if not assignment:
                        return json.dumps({"error": "You are not assigned to this project. Access denied."})

                    if assignment.custom_hourly_cost is not None:
                        cost_rate = float(assignment.custom_hourly_cost)
                    if assignment.custom_hourly_billing is not None:
                        billing_rate = float(assignment.custom_hourly_billing)

                hours_logged = float(data.get("hours_logged", 0.0))
                data["employee_cost"] = hours_logged * cost_rate
                data["billing_amount"] = hours_logged * billing_rate
                data["profit_loss"] = data["billing_amount"] - data["employee_cost"]

                # Save Task
                new_task = DeveloperTasks(**data)
                session.add(new_task)
                session.commit()
                session.refresh(new_task)
                
                logger.info(f"Developer Task Added | Emp: {employee.username} | Profit: ${data['profit_loss']}")
                return json.dumps(self.model_to_dict(new_task), indent=4, default=str)
            
            except ValueError as ve:
                session.rollback()
                return json.dumps({"error": "Invalid numerical data submitted for hours or rates.", "details": str(ve)})
            except Exception as e:
                session.rollback()
                return self._handle_error("add_developer_task", e, context=data)

    def add_content_creator_task(self, data: dict) -> str:
        """
        Calculation Engine Trigger: Intercepts social media task, auto-calculates 
        total content generated based on pieces.
        """
        with self.SessionLocal() as session:
            try:
                employee_id = data.get("employee_id")
                if not employee_id:
                    return json.dumps({"error": "employee_id is required for Content Tasks."})

                # --- PHASE 5: ADVANCED FINANCIAL AUTO-CALCULATION ---
                employee = session.query(Employees).filter_by(id=employee_id).first()
                if not employee:
                    return json.dumps({"error": f"Employee {employee_id} not found."})

                project_id = data.get("project_id")
                cost_rate = float(employee.hourly_cost_rate or 0.0)
                billing_rate = float(employee.hourly_billing_rate or 0.0)

                # Intercept logic: If working on a specific project, check for custom whitelist rates
                if project_id:
                    assignment = session.query(ProjectAssignments).filter_by(
                        project_id=project_id, 
                        employee_id=employee_id
                    ).first()
                    
                    if not assignment:
                        return json.dumps({"error": "You are not assigned to this project. Access denied."})

                    if assignment.custom_hourly_cost is not None:
                        cost_rate = float(assignment.custom_hourly_cost)
                    if assignment.custom_hourly_billing is not None:
                        billing_rate = float(assignment.custom_hourly_billing)

                hours_logged = float(data.get("hours_logged", 0.0))
                data["employee_cost"] = hours_logged * cost_rate
                data["billing_amount"] = hours_logged * billing_rate
                data["profit_loss"] = data["billing_amount"] - data["employee_cost"]

                # CONTENT AGGREGATION AUTO-CALCULATION
                reels = int(data.get("reels_count", 0))
                long_videos = int(data.get("long_video_count", 0))
                posters = int(data.get("poster_count", 0))
                
                data["total_content"] = reels + long_videos + posters

                # Save Task
                new_task = ContentCreatorTasks(**data)
                session.add(new_task)
                session.commit()
                session.refresh(new_task)

                logger.info(f"Content Task Added | EmpID: {employee_id} | Total Content: {data['total_content']}")
                return json.dumps(self.model_to_dict(new_task), indent=4, default=str)
            
            except ValueError as ve:
                session.rollback()
                return json.dumps({"error": "Invalid numerical data submitted for content counts.", "details": str(ve)})
            except Exception as e:
                session.rollback()
                return self._handle_error("add_content_creator_task", e, context=data)

    def get_all_tasks(self) -> str:
        """Utility to fetch all tasks from both tables, usually for high-level overviews."""
        with self.SessionLocal() as session:
            try:
                dev_tasks = session.query(DeveloperTasks).all()
                content_tasks = session.query(ContentCreatorTasks).all()
                
                combined = []
                for dt in dev_tasks:
                    d = self.model_to_dict(dt)
                    d['task_type'] = 'developer'
                    combined.append(d)
                for ct in content_tasks:
                    c = self.model_to_dict(ct)
                    c['task_type'] = 'content_creator'
                    combined.append(c)

                return json.dumps(combined, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_all_tasks", e)

    # ==========================================
    #     PROJECTS, SRS, & TIMELINE (PHASE 2)
    # ==========================================

    def add_project(self, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                new_project = Projects(**data)
                session.add(new_project)
                session.commit()
                session.refresh(new_project)
                return json.dumps(self.model_to_dict(new_project), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("add_project", e, context=data)

    def _calculate_project_progress(self, session, proj) -> str:
        """Helper to dynamically calculate progress based on burn vs budget"""
        try:
            budget = float(proj.budget or 0)
            if budget <= 0:
                return proj.progress or "N/A"
            
            from sqlalchemy import func
            d_cost = session.query(func.coalesce(func.sum(DeveloperTasks.employee_cost), 0)).filter(DeveloperTasks.project_id == proj.id).scalar()
            c_cost = session.query(func.coalesce(func.sum(ContentCreatorTasks.employee_cost), 0)).filter(ContentCreatorTasks.project_id == proj.id).scalar()
            
            total_cost = float(d_cost) + float(c_cost)
            progress_pct = min(100, int((total_cost / budget) * 100))
            return f"{progress_pct}%"
        except Exception:
            return proj.progress or "N/A"

    def get_all_projects(self) -> str:
        with self.SessionLocal() as session:
            try:
                projects = session.query(Projects).all()
                res_list = []
                for p in projects:
                    p_dict = self.model_to_dict(p)
                    p_dict['progress'] = self._calculate_project_progress(session, p)
                    res_list.append(p_dict)
                return json.dumps(res_list, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_all_projects", e)

    def add_srs_document(self, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                new_srs = SRS_Documents(**data)
                session.add(new_srs)
                session.commit()
                session.refresh(new_srs)
                return json.dumps(self.model_to_dict(new_srs), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("add_srs_document", e, context=data)

    def get_srs_by_project(self, project_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                documents = session.query(SRS_Documents).filter_by(project_id=project_id).order_by(SRS_Documents.created_at.desc()).all()
                return json.dumps([self.model_to_dict(d) for d in documents], indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_srs_by_project", e)

    def delete_srs_document(self, srs_id: str) -> str:
        import os
        with self.SessionLocal() as session:
            try:
                document = session.query(SRS_Documents).filter_by(id=srs_id).first()
                if not document:
                    return json.dumps({"error": "SRS document not found"})
                
                # If local file, delete it
                if document.file_url_or_path and not document.file_url_or_path.startswith("http"):
                    if os.path.exists(document.file_url_or_path):
                        os.remove(document.file_url_or_path)
                
                session.delete(document)
                session.commit()
                return json.dumps({"message": "SRS document deleted successfully"})
            except Exception as e:
                session.rollback()
                return self._handle_error("delete_srs_document", e, context={"srs_id": srs_id})


    def add_project_timeline(self, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                new_milestone = ProjectTimeline(**data)
                session.add(new_milestone)
                session.commit()
                session.refresh(new_milestone)
                return json.dumps(self.model_to_dict(new_milestone), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("add_project_timeline", e, context=data)

    def get_project_timeline(self, project_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                timeline = session.query(ProjectTimeline).filter_by(project_id=project_id).order_by(ProjectTimeline.expected_start).all()
                res_list = [self.model_to_dict(t) for t in timeline]
                return json.dumps(res_list, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_project_timeline", e, context={"project_id": project_id})

    # ==========================================
    #     PROJECT ASSIGNMENTS (PHASE 5)
    # ==========================================

    def assign_employee_to_project(self, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                # Check if already assigned
                existing = session.query(ProjectAssignments).filter_by(
                    project_id=data.get("project_id"),
                    employee_id=data.get("employee_id")
                ).first()
                if existing:
                    return json.dumps({"error": "Employee is already assigned to this project."})
                
                new_assignment = ProjectAssignments(**data)
                session.add(new_assignment)
                session.commit()
                session.refresh(new_assignment)
                return json.dumps(self.model_to_dict(new_assignment), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("assign_employee_to_project", e, context=data)

    def get_project_assignments(self, project_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                # Need to join with Employees and Departments_Roles to get names/rates/roles
                assignments = session.query(ProjectAssignments, Employees, Departments_Roles).join(
                    Employees, ProjectAssignments.employee_id == Employees.id
                ).outerjoin(
                    Departments_Roles, Employees.role_id == Departments_Roles.id
                ).filter(ProjectAssignments.project_id == project_id).all()
                
                res_list = []
                for assign, emp, role in assignments:
                    a_dict = self.model_to_dict(assign)
                    # Add employee details
                    a_dict['full_name'] = emp.full_name
                    a_dict['job_title'] = role.role_name if role else "Employee"
                    a_dict['hourly_cost_rate'] = emp.hourly_cost_rate
                    a_dict['hourly_billing_rate'] = emp.hourly_billing_rate
                    res_list.append(a_dict)
                    
                return json.dumps(res_list, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_project_assignments", e, context={"project_id": project_id})

    def unassign_employee(self, assignment_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                assignment = session.query(ProjectAssignments).filter_by(id=assignment_id).first()
                if not assignment:
                    return json.dumps({"error": "Assignment not found."})
                session.delete(assignment)
                session.commit()
                return json.dumps({"message": "Employee unassigned successfully."})
            except Exception as e:
                session.rollback()
                return self._handle_error("unassign_employee", e, context={"assignment_id": assignment_id})

    def get_employee_projects(self, employee_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                # Find all project assignments for this employee
                assignments = session.query(ProjectAssignments, Projects).join(
                    Projects, ProjectAssignments.project_id == Projects.id
                ).filter(ProjectAssignments.employee_id == employee_id).all()
                
                res_list = []
                for assign, proj in assignments:
                    p_dict = self.model_to_dict(proj)
                    res_list.append(p_dict)
                    
                return json.dumps(res_list, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_employee_projects", e, context={"employee_id": employee_id})

    # ==========================================
    #          AUDIT & COMPLIANCE
    # ==========================================

    def log_login_history(self, user_id: str, user_role: str, ip_address: str = "Unknown", user_agent: str = "Unknown") -> None:
        """Fire-and-forget logging function for tracking security access."""
        with self.SessionLocal() as session:
            try:
                log_entry = LoginHistory(
                    user_id=user_id,
                    user_role=user_role,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                session.add(log_entry)
                session.commit()
                logger.info(f"LOGIN SUCCESS: {user_role} ({user_id}) from {ip_address}")
            except Exception as e:
                session.rollback()
                # We do not return JSON here because this is called passively during login flows.
                logger.error(f"Failed to log login history for user {user_id}: {str(e)}", exc_info=True)

    # ==========================================
    #     REMAINING CRUD OPERATIONS (PHASE 2)
    # ==========================================

    def get_employee(self, employee_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                emp = session.query(Employees).filter_by(id=employee_id).first()
                if not emp:
                    return json.dumps({"error": "Employee not found"})
                res = self.model_to_dict(emp)
                res.pop('password', None)
                return json.dumps(res, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_employee", e)

    def delete_employee(self, employee_id: str) -> str:
        import os
        import shutil
        with self.SessionLocal() as session:
            try:
                emp = session.query(Employees).filter_by(id=employee_id).first()
                if not emp:
                    return json.dumps({"error": "Employee not found"})

                # --- CLEANUP: Delete the employee's upload folder from disk ---
                upload_folder = os.path.join("data", "uploads", "employees", employee_id)
                if os.path.isdir(upload_folder):
                    shutil.rmtree(upload_folder)
                    logger.info(f"Deleted employee upload folder: {upload_folder}")

                session.delete(emp)
                session.commit()
                return json.dumps({"message": "Employee and all associated documents deleted successfully"})
            except Exception as e:
                session.rollback()
                return self._handle_error("delete_employee", e)

    def get_project(self, project_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                proj = session.query(Projects).filter_by(id=project_id).first()
                if not proj:
                    return json.dumps({"error": "Project not found"})
                
                p_dict = self.model_to_dict(proj)
                p_dict['progress'] = self._calculate_project_progress(session, proj)
                return json.dumps(p_dict, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_project", e)

    def edit_project(self, project_id: str, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                proj = session.query(Projects).filter_by(id=project_id).first()
                if not proj:
                    return json.dumps({"error": "Project not found"})
                for key, value in data.items():
                    setattr(proj, key, value)
                session.commit()
                session.refresh(proj)
                return json.dumps(self.model_to_dict(proj), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("edit_project", e, context={"project_id": project_id})

    def delete_project(self, project_id: str) -> str:
        import os
        import shutil
        import glob
        with self.SessionLocal() as session:
            try:
                proj = session.query(Projects).filter_by(id=project_id).first()
                if not proj:
                    return json.dumps({"error": "Project not found"})

                # --- CLEANUP: Delete all SRS files from disk ---
                srs_docs = session.query(SRS_Documents).filter_by(project_id=project_id).all()
                for doc in srs_docs:
                    if doc.file_url_or_path and not doc.file_url_or_path.startswith("http"):
                        if os.path.exists(doc.file_url_or_path):
                            os.remove(doc.file_url_or_path)
                            logger.info(f"Deleted SRS file: {doc.file_url_or_path}")

                # Delete the project's entire upload folder (data/uploads/projects/{project_id}_*)
                upload_pattern = os.path.join("data", "uploads", "projects", f"{project_id}_*")
                for folder_path in glob.glob(upload_pattern):
                    if os.path.isdir(folder_path):
                        shutil.rmtree(folder_path)
                        logger.info(f"Deleted SRS upload folder: {folder_path}")

                # Delete the project (cascading deletes will handle DB child records)
                session.delete(proj)
                session.commit()
                return json.dumps({"message": "Project and all associated SRS files deleted successfully"})
            except Exception as e:
                session.rollback()
                return self._handle_error("delete_project", e)

    def get_task(self, task_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                # Search Developer Tasks first
                task = session.query(DeveloperTasks).filter_by(id=task_id).first()
                if task:
                    res = self.model_to_dict(task)
                    res['task_type'] = 'developer'
                    return json.dumps(res, indent=4, default=str)
                
                # Search Content Tasks second
                task = session.query(ContentCreatorTasks).filter_by(id=task_id).first()
                if task:
                    res = self.model_to_dict(task)
                    res['task_type'] = 'content_creator'
                    return json.dumps(res, indent=4, default=str)
                
                return json.dumps({"error": "Task not found"})
            except Exception as e:
                return self._handle_error("get_task", e)

    def delete_task(self, task_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                # Find the task in either table
                task = session.query(DeveloperTasks).filter_by(id=task_id).first()
                if not task:
                    task = session.query(ContentCreatorTasks).filter_by(id=task_id).first()
                    
                if not task:
                    return json.dumps({"error": "Task not found"})
                    
                session.delete(task)
                session.commit()
                return json.dumps({"message": "Task deleted successfully"})
            except Exception as e:
                session.rollback()
                return self._handle_error("delete_task", e)

    def get_tasks_by_employee(self, employee_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                dev_tasks = session.query(DeveloperTasks).filter_by(employee_id=employee_id).all()
                content_tasks = session.query(ContentCreatorTasks).filter_by(employee_id=employee_id).all()
                
                combined = []
                for dt in dev_tasks:
                    d = self.model_to_dict(dt)
                    d['task_type'] = 'developer'
                    combined.append(d)
                for ct in content_tasks:
                    c = self.model_to_dict(ct)
                    c['task_type'] = 'content_creator'
                    combined.append(c)
                    
                return json.dumps(combined, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_tasks_by_employee", e)

    # ==========================================
    #     EXTENDED CRUD: ADMINS, ROLES, TIMELINES, SRS & TASKS
    # ==========================================

    def get_all_admins(self) -> str:
        with self.SessionLocal() as session:
            try:
                admins = session.query(Admins).all()
                results = []
                for a in admins:
                    a_dict = self.model_to_dict(a)
                    a_dict.pop('password', None)
                    results.append(a_dict)
                return json.dumps(results, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_all_admins", e)

    def get_admin(self, admin_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                admin = session.query(Admins).filter_by(id=admin_id).first()
                if not admin:
                    return json.dumps({"error": "Admin not found"})
                res = self.model_to_dict(admin)
                res.pop('password', None)
                return json.dumps(res, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_admin", e)

    def edit_admin(self, admin_id: str, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                admin = session.query(Admins).filter_by(id=admin_id).first()
                if not admin:
                    return json.dumps({"error": "Admin not found"})
                for key, value in data.items():
                    if key == "password":
                        value = get_password_hash(value)
                    setattr(admin, key, value)
                session.commit()
                session.refresh(admin)
                res = self.model_to_dict(admin)
                res.pop('password', None)
                return json.dumps(res, indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("edit_admin", e, context={"admin_id": admin_id})

    def delete_admin(self, admin_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                admin = session.query(Admins).filter_by(id=admin_id).first()
                if not admin:
                    return json.dumps({"error": "Admin not found"})
                session.delete(admin)
                session.commit()
                return json.dumps({"message": "Admin deleted successfully"})
            except Exception as e:
                session.rollback()
                return self._handle_error("delete_admin", e)

    def edit_department_role(self, role_id: str, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                role = session.query(Departments_Roles).filter_by(id=role_id).first()
                if not role:
                    return json.dumps({"error": "Role not found"})
                for key, value in data.items():
                    setattr(role, key, value)
                session.commit()
                session.refresh(role)
                return json.dumps(self.model_to_dict(role), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("edit_department_role", e, context={"role_id": role_id})

    def delete_department_role(self, role_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                role = session.query(Departments_Roles).filter_by(id=role_id).first()
                if not role:
                    return json.dumps({"error": "Role not found"})
                session.delete(role)
                session.commit()
                return json.dumps({"message": "Role deleted successfully"})
            except Exception as e:
                session.rollback()
                return self._handle_error("delete_department_role", e)

    def edit_srs_document(self, srs_id: str, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                srs = session.query(SRS_Documents).filter_by(id=srs_id).first()
                if not srs:
                    return json.dumps({"error": "SRS not found"})
                for key, value in data.items():
                    setattr(srs, key, value)
                session.commit()
                session.refresh(srs)
                return json.dumps(self.model_to_dict(srs), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("edit_srs_document", e, context={"srs_id": srs_id})

    def delete_srs_document(self, srs_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                srs = session.query(SRS_Documents).filter_by(id=srs_id).first()
                if not srs:
                    return json.dumps({"error": "SRS not found"})
                session.delete(srs)
                session.commit()
                return json.dumps({"message": "SRS deleted successfully"})
            except Exception as e:
                session.rollback()
                return self._handle_error("delete_srs_document", e)

    def edit_project_timeline(self, timeline_id: str, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                timeline = session.query(ProjectTimeline).filter_by(id=timeline_id).first()
                if not timeline:
                    return json.dumps({"error": "Timeline milestone not found"})
                for key, value in data.items():
                    setattr(timeline, key, value)
                session.commit()
                session.refresh(timeline)
                return json.dumps(self.model_to_dict(timeline), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("edit_project_timeline", e, context={"timeline_id": timeline_id})

    def delete_project_timeline(self, timeline_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                timeline = session.query(ProjectTimeline).filter_by(id=timeline_id).first()
                if not timeline:
                    return json.dumps({"error": "Timeline milestone not found"})
                session.delete(timeline)
                session.commit()
                return json.dumps({"message": "Milestone deleted successfully"})
            except Exception as e:
                session.rollback()
                return self._handle_error("delete_project_timeline", e)

    def edit_developer_task(self, task_id: str, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                task = session.query(DeveloperTasks).filter_by(id=task_id).first()
                if not task:
                    return json.dumps({"error": "Developer Task not found."})
                
                for key, value in data.items():
                    setattr(task, key, value)
                
                # RE-CALCULATE FINANCIALS IF HOURS ARE EDITED
                if 'hours_logged' in data:
                    employee = session.query(Employees).filter_by(id=task.employee_id).first()
                    if employee:
                        cost_rate = float(employee.hourly_cost_rate or 0.0)
                        billing_rate = float(employee.hourly_billing_rate or 0.0)
                        task.employee_cost = float(task.hours_logged) * cost_rate
                        task.billing_amount = float(task.hours_logged) * billing_rate
                        task.profit_loss = task.billing_amount - task.employee_cost

                session.commit()
                session.refresh(task)
                res = self.model_to_dict(task)
                res['task_type'] = 'developer'
                return json.dumps(res, indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("edit_developer_task", e, context={"task_id": task_id})

    def edit_content_creator_task(self, task_id: str, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                task = session.query(ContentCreatorTasks).filter_by(id=task_id).first()
                if not task:
                    return json.dumps({"error": "Content Task not found."})
                
                for key, value in data.items():
                    setattr(task, key, value)
                
                # RE-CALCULATE TOTAL CONTENT IF COUNTS ARE EDITED
                if any(k in data for k in ['reels_count', 'long_video_count', 'poster_count']):
                    task.total_content = (task.reels_count or 0) + (task.long_video_count or 0) + (task.poster_count or 0)

                session.commit()
                session.refresh(task)
                res = self.model_to_dict(task)
                res['task_type'] = 'content_creator'
                return json.dumps(res, indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("edit_content_creator_task", e, context={"task_id": task_id})