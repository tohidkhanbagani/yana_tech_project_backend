import os
import shutil
import glob

import uuid as _uuid
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError, NoResultFound
from sqlalchemy.inspection import inspect
from sqlalchemy import cast, Date, func, case
from passlib.context import CryptContext

from .database_create import SessionLocal
from .database_tables import (
    Departments_Roles, Admins, Employees, LoginHistory, Managers,
    Projects, SRS_Documents, ProjectTimeline, ProjectAssignments, MilestoneAssignments,
    DeveloperTasks, ContentCreatorTasks, ProjectExpenses, Attendance, LeaveRequest, ProjectPayments,
    ChecklistTemplate, ProjectChecklistState
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
    #              MANAGERS
    # ==========================================

    def add_manager(self, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                new_manager = Managers(**data)
                session.add(new_manager)
                session.commit()
                session.refresh(new_manager)
                return json.dumps(self.model_to_dict(new_manager), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("add_manager", e, context={"name": data.get("name")})

    def get_all_managers(self) -> str:
        with self.SessionLocal() as session:
            try:
                managers = session.query(Managers).all()
                return json.dumps([self.model_to_dict(m) for m in managers], indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_all_managers", e)

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
                default_password = data.get("password") or "AdminPass123!"
                data['password'] = get_password_hash(default_password)
                
                new_admin = Admins(**data)
                session.add(new_admin)
                session.commit()
                session.refresh(new_admin)
                
                # Automatically create Employee Profile and insert into Managers table if access_level is ManagerAdmin
                if new_admin.access_level == "ManagerAdmin":
                    # Create Employees profile
                    existing_emp = session.query(Employees).filter_by(username=new_admin.username).first()
                    if not existing_emp:
                        # Find a role with "manager" in name, or default role
                        manager_role = session.query(Departments_Roles).filter(Departments_Roles.role_name.ilike("%manager%")).first()
                        role_id = manager_role.id if manager_role else None
                        
                        # Generate unique email if N/A
                        email_val = new_admin.email if new_admin.email and new_admin.email != "N/A" else f"{new_admin.username}@yanatech.com"
                        
                        new_emp = Employees(
                            username=new_admin.username,
                            password=new_admin.password,
                            # plain_password=default_password,
                            full_name=new_admin.full_name if new_admin.full_name and new_admin.full_name != "N/A" else new_admin.username,
                            email=email_val,
                            role_id=role_id,
                            is_active=True
                        )
                        session.add(new_emp)
                    
                    # Insert into Managers registry
                    mgr_name = new_admin.full_name if new_admin.full_name and new_admin.full_name != "N/A" else new_admin.username
                    existing_mgr = session.query(Managers).filter_by(name=mgr_name).first()
                    if not existing_mgr:
                        new_mgr = Managers(name=mgr_name)
                        session.add(new_mgr)
                    
                    session.commit()
                
                # Strip password from return dict for security
                res_dict = self.model_to_dict(new_admin)
                res_dict.pop('password', None)
                res_dict['generated_password'] = default_password # Expose plaintext once
                
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
                # data["plain_password"] = default_password

                # 2.5 Salary -> Hourly Cost Auto-calculation
                salary_val = float(data.get("salary") or 0.0)
                data["hourly_cost_rate"] = salary_val / (26 * 8)

                # Remove extra fields not in table
                data.pop("department", None)

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
                    if hasattr(employee, key):
                        if key == "password":
                            value = get_password_hash(value)
                        setattr(employee, key, value)
                
                # Auto-recalculate hourly cost rate when salary is edited
                if "salary" in data:
                    employee.hourly_cost_rate = float(data["salary"] or 0.0) / (26 * 8)
                
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
                
                # --- ATTENDANCE CHECK-IN/CHECK-OUT ENFORCEMENT ---
                task_date_val = data.get("date")
                if not task_date_val:
                    task_date = datetime.now()
                elif isinstance(task_date_val, datetime):
                    task_date = task_date_val
                elif hasattr(task_date_val, "date"):
                    task_date = datetime.combine(task_date_val, datetime.min.time())
                elif isinstance(task_date_val, str):
                    parsed = None
                    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                        try:
                            parsed = datetime.strptime(task_date_val.split("+")[0].split("Z")[0], fmt)
                            break
                        except ValueError:
                            continue
                    if parsed is None:
                        try:
                            parsed = datetime.fromisoformat(task_date_val)
                        except ValueError:
                            pass
                    task_date = parsed if parsed is not None else datetime.now()
                else:
                    task_date = datetime.now()

                # Normalize to date to perform date.between check
                task_cal_date = task_date.date()
                start_of_day = datetime.combine(task_cal_date, datetime.min.time())
                end_of_day = datetime.combine(task_cal_date, datetime.max.time())

                attendance = session.query(Attendance).filter(
                    Attendance.employee_id == employee_id,
                    Attendance.date.between(start_of_day, end_of_day)
                ).first()

                if not attendance:
                    return json.dumps({"error": "Access Denied: You must check in before logging any tasks."})
                if attendance.check_out_time is not None:
                    return json.dumps({"error": "Access Denied: You cannot log tasks after checking out."})

                # Store the parsed datetime in data
                data["date"] = task_date

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

                    if assignment.custom_hourly_billing is not None:
                        billing_rate = float(assignment.custom_hourly_billing)

                hours_logged = float(data.get("hours_logged", 0.0))
                data["employee_cost"] = hours_logged * cost_rate
                data["billing_amount"] = hours_logged * billing_rate
                data["profit_loss"] = data["billing_amount"] - data["employee_cost"]

                # Save Task
                new_task = DeveloperTasks(**data)
                session.add(new_task)
                
                # Check and update milestone status and actual_start date
                milestone_id = data.get("milestone_id")
                if milestone_id:
                    milestone = session.query(ProjectTimeline).filter_by(id=milestone_id).first()
                    if milestone:
                        if milestone.status == 'Pending':
                            milestone.status = 'Active'
                        if not milestone.actual_start:
                            milestone.actual_start = datetime.now()
                        
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

                # --- ATTENDANCE CHECK-IN/CHECK-OUT ENFORCEMENT ---
                task_date_val = data.get("date")
                if not task_date_val:
                    task_date = datetime.now()
                elif isinstance(task_date_val, datetime):
                    task_date = task_date_val
                elif hasattr(task_date_val, "date"):
                    task_date = datetime.combine(task_date_val, datetime.min.time())
                elif isinstance(task_date_val, str):
                    parsed = None
                    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                        try:
                            parsed = datetime.strptime(task_date_val.split("+")[0].split("Z")[0], fmt)
                            break
                        except ValueError:
                            continue
                    if parsed is None:
                        try:
                            parsed = datetime.fromisoformat(task_date_val)
                        except ValueError:
                            pass
                    task_date = parsed if parsed is not None else datetime.now()
                else:
                    task_date = datetime.now()

                # Normalize to date to perform date.between check
                task_cal_date = task_date.date()
                start_of_day = datetime.combine(task_cal_date, datetime.min.time())
                end_of_day = datetime.combine(task_cal_date, datetime.max.time())

                attendance = session.query(Attendance).filter(
                    Attendance.employee_id == employee_id,
                    Attendance.date.between(start_of_day, end_of_day)
                ).first()

                if not attendance:
                    return json.dumps({"error": "Access Denied: You must check in before logging any tasks."})
                if attendance.check_out_time is not None:
                    return json.dumps({"error": "Access Denied: You cannot log tasks after checking out."})

                # Store the parsed datetime in data
                data["date"] = task_date

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
                
                # Check and update milestone status and actual_start date
                milestone_id = data.get("milestone_id")
                if milestone_id:
                    milestone = session.query(ProjectTimeline).filter_by(id=milestone_id).first()
                    if milestone:
                        if milestone.status == 'Pending':
                            milestone.status = 'Active'
                        if not milestone.actual_start:
                            milestone.actual_start = datetime.now()
                        
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
                valid_keys = {c.key for c in inspect(Projects).mapper.column_attrs}
                filtered_data = {k: v for k, v in data.items() if k in valid_keys}
                new_project = Projects(**filtered_data)
                session.add(new_project)
                session.commit()
                session.refresh(new_project)
                return json.dumps(self.model_to_dict(new_project), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("add_project", e, context=data)

    def _calculate_project_progress(self, session, proj) -> str:
        """
        System of Control Fix: Progress is now measured by Work Done (Milestones), 
        not by Money Spent (Budget).
        Falls back to manually set database progress if no milestones are defined.
        """
        try:
            total_milestones = session.query(ProjectTimeline).filter_by(project_id=proj.id).count()
            if total_milestones == 0:
                return proj.progress if hasattr(proj, 'progress') and proj.progress else "0%"
            
            completed_milestones = session.query(ProjectTimeline).filter(
                ProjectTimeline.project_id == proj.id,
                ProjectTimeline.status.ilike("%completed%")
            ).count()
            
            progress_pct = int((completed_milestones / total_milestones) * 100)
            return f"{progress_pct}%"
        except Exception:
            return proj.progress if hasattr(proj, 'progress') and proj.progress else "0%"

    def _calculate_payment_stats(self, session, proj) -> dict:
        """
        Computes the financial state of a project on the fly.
        """
        try:
            payments = session.query(ProjectPayments).filter_by(project_id=proj.id).all()
            total_paid = sum(p.amount for p in payments)
            client_cost = float(proj.client_cost or 0.0)
            pending_amount = max(0.0, client_cost - total_paid)
            
            if total_paid >= client_cost and client_cost > 0:
                payment_status = "Paid in Full"
            elif total_paid > 0:
                payment_status = "Partial"
            else:
                payment_status = "Unpaid"
                
            return {
                "total_paid": total_paid,
                "pending_amount": pending_amount,
                "payment_status": payment_status
            }
        except Exception:
            return {
                "total_paid": 0.0,
                "pending_amount": float(proj.client_cost or 0.0),
                "payment_status": "Unpaid"
            }

    def get_all_projects(self) -> str:
        with self.SessionLocal() as session:
            try:
                # Aggregate Payments
                payment_agg = session.query(
                    ProjectPayments.project_id,
                    func.sum(ProjectPayments.amount).label("total_paid")
                ).group_by(ProjectPayments.project_id).subquery()
                
                # Aggregate Timeline (Milestones)
                timeline_agg = session.query(
                    ProjectTimeline.project_id,
                    func.count(ProjectTimeline.id).label("total_milestones"),
                    func.sum(case((ProjectTimeline.status.ilike("%completed%"), 1), else_=0)).label("completed_milestones")
                ).group_by(ProjectTimeline.project_id).subquery()
                
                # Main Query with Joins
                query = session.query(
                    Projects,
                    func.coalesce(payment_agg.c.total_paid, 0).label("total_paid"),
                    func.coalesce(timeline_agg.c.total_milestones, 0).label("total_milestones"),
                    func.coalesce(timeline_agg.c.completed_milestones, 0).label("completed_milestones")
                ).outerjoin(
                    payment_agg, Projects.id == payment_agg.c.project_id
                ).outerjoin(
                    timeline_agg, Projects.id == timeline_agg.c.project_id
                )
                
                results = query.all()
                
                res_list = []
                for proj, total_paid, total_milestones, completed_milestones in results:
                    p_dict = self.model_to_dict(proj)
                    
                    # Progress calculation
                    if total_milestones > 0:
                        p_dict['progress'] = f"{int((completed_milestones / total_milestones) * 100)}%"
                    else:
                        p_dict['progress'] = proj.progress if hasattr(proj, 'progress') and proj.progress else "0%"
                        
                    # Payment calculation
                    client_cost = float(proj.client_cost or 0.0)
                    total_paid = float(total_paid or 0.0)
                    pending_amount = max(0.0, client_cost - total_paid)
                    
                    if total_paid >= client_cost and client_cost > 0:
                        payment_status = "Paid in Full"
                    elif total_paid > 0:
                        payment_status = "Partial"
                    else:
                        payment_status = "Unpaid"
                        
                    p_dict['total_paid'] = total_paid
                    p_dict['pending_amount'] = pending_amount
                    p_dict['payment_status'] = payment_status
                    
                    res_list.append(p_dict)
                    
                return json.dumps(res_list, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_all_projects", e)

    def add_srs_document(self, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                new_srs = SRS_Documents(**data)
                session.add(new_srs)
                session.flush() # Ensure ID is generated
                
                # Link the active SRS to the Project
                project_id = data.get("project_id")
                if project_id:
                    project = session.query(Projects).filter_by(id=project_id).first()
                    if project:
                        project.srs_id = new_srs.id
                        
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
                session.flush()

                project_id = new_milestone.project_id
                total = session.query(func.count(ProjectTimeline.id)).filter_by(project_id=project_id).scalar()
                if total and total > 0:
                    completed = session.query(func.count(ProjectTimeline.id)).filter(
                        ProjectTimeline.project_id == project_id,
                        ProjectTimeline.status.ilike('%completed%')
                    ).scalar()
                    proj = session.query(Projects).filter_by(id=project_id).first()
                    if proj:
                        proj.progress = f"{int((completed / total) * 100)}%"

                session.commit()
                session.refresh(new_milestone)
                return json.dumps(self.model_to_dict(new_milestone), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("add_project_timeline", e, context=data)

    def get_project_timeline(self, project_id: str, employee_id: str = None) -> str:
        with self.SessionLocal() as session:
            try:
                query = session.query(ProjectTimeline).filter_by(project_id=project_id)
                
                if employee_id:
                    # Filter milestones to show only those where the employee is assigned
                    query = query.join(
                        MilestoneAssignments, ProjectTimeline.id == MilestoneAssignments.milestone_id
                    ).filter(MilestoneAssignments.employee_id == employee_id)
                
                timeline = query.order_by(ProjectTimeline.expected_start).all()
                res_list = [self.model_to_dict(t) for t in timeline]
                return json.dumps(res_list, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_project_timeline", e, context={"project_id": project_id})
                
    def assign_employee_to_milestone(self, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                existing = session.query(MilestoneAssignments).filter_by(
                    milestone_id=data.get("milestone_id"),
                    employee_id=data.get("employee_id")
                ).first()
                if existing:
                    return json.dumps({"error": "Employee is already assigned to this milestone."})
                
                new_assignment = MilestoneAssignments(**data)
                session.add(new_assignment)
                session.commit()
                session.refresh(new_assignment)
                return json.dumps(self.model_to_dict(new_assignment), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("assign_employee_to_milestone", e, context=data)

    def get_milestone_assignments(self, milestone_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                assignments = session.query(MilestoneAssignments, Employees, Departments_Roles).join(
                    Employees, MilestoneAssignments.employee_id == Employees.id
                ).outerjoin(
                    Departments_Roles, Employees.role_id == Departments_Roles.id
                ).filter(MilestoneAssignments.milestone_id == milestone_id).all()
                
                res_list = []
                for assign, emp, role in assignments:
                    a_dict = self.model_to_dict(assign)
                    a_dict['full_name'] = emp.full_name
                    a_dict['job_title'] = role.role_name if role else "Employee"
                    a_dict['photo'] = emp.photo
                    res_list.append(a_dict)
                    
                return json.dumps(res_list, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_milestone_assignments", e, context={"milestone_id": milestone_id})

    def unassign_employee_from_milestone(self, assignment_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                assignment = session.query(MilestoneAssignments).filter_by(id=assignment_id).first()
                if not assignment:
                    return json.dumps({"error": "Milestone assignment not found."})
                session.delete(assignment)
                session.commit()
                return json.dumps({"message": "Employee unassigned from milestone successfully."})
            except Exception as e:
                session.rollback()
                return self._handle_error("unassign_employee_from_milestone", e, context={"assignment_id": assignment_id})

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
                    p_dict['progress'] = self._calculate_project_progress(session, proj)
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
                    login_timestamp=datetime.utcnow(),  # Record login timestamps in UTC!
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

    def parse_user_agent(self, user_agent: str) -> tuple:
        """Parses user agent to return a tuple of (browser, device/OS) as human-readable strings."""
        if not user_agent or user_agent == "Unknown":
            return "Unknown", "Unknown"
        
        ua = user_agent.lower()
        
        # Determine OS / Device
        if "windows phone" in ua:
            device = "Windows Phone"
        elif "win" in ua:
            if "nt 10.0" in ua:
                device = "Windows 10/11"
            elif "nt 6.3" in ua:
                device = "Windows 8.1"
            elif "nt 6.2" in ua:
                device = "Windows 8"
            elif "nt 6.1" in ua:
                device = "Windows 7"
            else:
                device = "Windows"
        elif "android" in ua:
            device = "Android Device"
        elif "ipad" in ua:
            device = "iPad"
        elif "iphone" in ua:
            device = "iPhone"
        elif "mac" in ua:
            device = "macOS"
        elif "linux" in ua:
            device = "Linux"
        else:
            device = "Other Device"
            
        # Determine Browser
        if "edg" in ua:
            browser = "Microsoft Edge"
        elif "chrome" in ua or "crios" in ua:
            browser = "Google Chrome"
        elif "safari" in ua:
            browser = "Apple Safari"
        elif "firefox" in ua or "fxios" in ua:
            browser = "Mozilla Firefox"
        elif "opr" in ua or "opera" in ua:
            browser = "Opera"
        elif "msie" in ua or "trident" in ua:
            browser = "Internet Explorer"
        else:
            browser = "Other Browser"
            
        return browser, device

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

                # Fetch Assignments
                assignments = session.query(ProjectAssignments).filter_by(project_id=project_id).all()
                assigned_employees = []
                for assign in assignments:
                    emp = session.query(Employees).filter_by(id=assign.employee_id).first()
                    if emp:
                        e_dict = self.model_to_dict(emp)
                        e_dict['custom_hourly_cost'] = assign.custom_hourly_cost
                        e_dict['custom_hourly_billing'] = assign.custom_hourly_billing
                        assigned_employees.append(e_dict)
                
                p_dict['assigned_employees'] = assigned_employees
                p_dict['progress'] = self._calculate_project_progress(session, proj)
                
                # Compute Payment Stats
                pay_stats = self._calculate_payment_stats(session, proj)
                p_dict.update(pay_stats)
                
                return json.dumps(p_dict, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_project", e)

    def export_project_csv_data(self, project_id: str) -> Optional[str]:
        import csv
        import io
        
        with self.SessionLocal() as session:
            try:
                # 1. Fetch core project details
                proj = session.query(Projects).filter_by(id=project_id).first()
                if not proj:
                    return None
                
                # Fetch related data
                # Assignments
                assignments = session.query(ProjectAssignments, Employees, Departments_Roles).join(
                    Employees, ProjectAssignments.employee_id == Employees.id
                ).outerjoin(
                    Departments_Roles, Employees.role_id == Departments_Roles.id
                ).filter(ProjectAssignments.project_id == project_id).all()
                
                # Timeline
                timeline = session.query(ProjectTimeline).filter_by(project_id=project_id).order_by(ProjectTimeline.expected_start).all()
                
                # Payments
                payments = session.query(ProjectPayments).filter_by(project_id=project_id).order_by(ProjectPayments.payment_date.desc()).all()
                
                # Expenses
                expenses = session.query(ProjectExpenses).filter_by(project_id=project_id).order_by(ProjectExpenses.expense_date.desc()).all()
                
                # Developer Tasks
                dev_tasks = session.query(DeveloperTasks, Employees).join(
                    Employees, DeveloperTasks.employee_id == Employees.id
                ).filter(DeveloperTasks.project_id == project_id).order_by(DeveloperTasks.date.desc()).all()
                
                # Content Creator Tasks
                content_tasks = session.query(ContentCreatorTasks, Employees).join(
                    Employees, ContentCreatorTasks.employee_id == Employees.id
                ).filter(ContentCreatorTasks.project_id == project_id).order_by(ContentCreatorTasks.date.desc()).all()
                
                # Checklist items
                checklists = session.query(ProjectChecklistState, ChecklistTemplate).join(
                    ChecklistTemplate, ProjectChecklistState.checklist_id == ChecklistTemplate.id
                ).filter(ProjectChecklistState.project_id == project_id).all()
                
                # SRS
                srs_docs = session.query(SRS_Documents).filter_by(project_id=project_id).order_by(SRS_Documents.created_at.desc()).all()
                
                # Setup CSV writer
                output = io.StringIO()
                writer = csv.writer(output, lineterminator='\n')
                
                # --- SECTION 1: PROJECT METADATA ---
                writer.writerow(["=== PROJECT METADATA ==="])
                writer.writerow([
                    "Project ID", "Project Name", "Project Type", "Description", "Status",
                    "Client Cost", "Budget", "Approx Cost", "Cost Type", "Start Date",
                    "End Date", "Progress", "Manager", "Client Name", "Team", 
                    "Referred By", "Filled By", "Assigned To", "Created At", "Updated At"
                ])
                writer.writerow([
                    proj.id, proj.name, proj.project_type, proj.description, proj.status,
                    proj.client_cost, proj.budget, proj.approx_cost, proj.cost_type, proj.start_date,
                    proj.end_date, self._calculate_project_progress(session, proj), proj.manager, proj.client, proj.team,
                    proj.referred_by, proj.filled_by, proj.assigned_to, proj.created_at, proj.updated_at
                ])
                writer.writerow([]) # Empty spacer
                
                # --- SECTION 2: ASSIGNED TEAM MEMBERS ---
                writer.writerow(["=== ASSIGNED TEAM MEMBERS ==="])
                writer.writerow([
                    "Employee ID", "Full Name", "Email", "Role/Job Title", 
                    "Standard Cost Rate", "Standard Billing Rate", "Custom Cost Override", "Custom Billing Override", "Assigned At"
                ])
                if assignments:
                    for assign, emp, role in assignments:
                        writer.writerow([
                            emp.id, emp.full_name, emp.email, role.role_name if role else "Employee",
                            emp.hourly_cost_rate, emp.hourly_billing_rate, assign.custom_hourly_cost, assign.custom_hourly_billing, assign.assigned_at
                        ])
                else:
                    writer.writerow(["No team members assigned."])
                writer.writerow([])
                
                # --- SECTION 3: PROJECT TIMELINE & MILESTONES ---
                writer.writerow(["=== PROJECT TIMELINE & MILESTONES ==="])
                writer.writerow([
                    "Milestone ID", "Milestone Name", "Expected Start", "Expected End", 
                    "Actual Start", "Actual End", "Status", "Remarks", "Created At"
                ])
                if timeline:
                    for t in timeline:
                        writer.writerow([
                            t.id, t.milestone_name, t.expected_start, t.expected_end,
                            t.actual_start, t.actual_end, t.status, t.remarks, t.created_at
                        ])
                else:
                    writer.writerow(["No timeline milestones defined."])
                writer.writerow([])
                
                # --- SECTION 4: CLIENT PAYMENT HISTORY ---
                writer.writerow(["=== CLIENT PAYMENT HISTORY ==="])
                writer.writerow([
                    "Payment ID", "Amount", "Payment Date", "Payment Method", "Reference Number", "Remarks", "Logged At"
                ])
                if payments:
                    for p in payments:
                        writer.writerow([
                            p.id, p.amount, p.payment_date, p.payment_method, p.reference_number, p.remarks, p.created_at
                        ])
                else:
                    writer.writerow(["No client payments logged."])
                writer.writerow([])
                
                # --- SECTION 5: PROJECT EXPENSES ---
                writer.writerow(["=== PROJECT EXPENSES ==="])
                writer.writerow([
                    "Expense ID", "Expense Name", "Amount", "Expense Date", "Description", "Logged At"
                ])
                if expenses:
                    for e in expenses:
                        writer.writerow([
                            e.id, e.expense_name, e.amount, e.expense_date, e.description, e.created_at
                        ])
                else:
                    writer.writerow(["No project expenses logged."])
                writer.writerow([])
                
                # --- SECTION 6: DEVELOPER TIMESHEETS ---
                writer.writerow(["=== DEVELOPER TIMESHEETS ==="])
                writer.writerow([
                    "Task ID", "Employee Name", "Date Logged", "Hours Logged", "Tech Stack Used", 
                    "GitHub Link", "Task Performed", "Tomorrow's Plan", "Employee Cost", "Billing Amount", "Profit/Loss", "Logged At"
                ])
                if dev_tasks:
                    for dt, emp in dev_tasks:
                        writer.writerow([
                            dt.id, emp.full_name, dt.date, dt.hours_logged, dt.tech_stack,
                            dt.github_link, dt.task_performed, dt.tomorrow_plan, dt.employee_cost, dt.billing_amount, dt.profit_loss, dt.created_at
                        ])
                else:
                    writer.writerow(["No developer tasks logged."])
                writer.writerow([])
                
                # --- SECTION 7: CONTENT CREATOR TIMESHEETS ---
                writer.writerow(["=== CONTENT CREATOR TIMESHEETS ==="])
                writer.writerow([
                    "Task ID", "Employee Name", "Date Logged", "Hours Logged", "Reels Count", "Long Video Count",
                    "Poster Count", "Calls Made", "Platform", "Total Content", "Task Performed", 
                    "Employee Cost", "Billing Amount", "Profit/Loss", "Logged At"
                ])
                if content_tasks:
                    for ct, emp in content_tasks:
                        writer.writerow([
                            ct.id, emp.full_name, ct.date, ct.hours_logged, ct.reels_count, ct.long_video_count,
                            ct.poster_count, ct.calls_made, ct.platform, ct.total_content, ct.task_performed,
                            ct.employee_cost, ct.billing_amount, ct.profit_loss, ct.created_at
                        ])
                else:
                    writer.writerow(["No content creator tasks logged."])
                writer.writerow([])
                
                # --- SECTION 8: GATEKEEPER CHECKLIST ---
                writer.writerow(["=== GATEKEEPER CHECKLIST ==="])
                writer.writerow([
                    "Checklist Item ID", "Phase", "Task Description", "Completed State", "Last Updated"
                ])
                if checklists:
                    for state_item, template in checklists:
                        writer.writerow([
                            state_item.id, template.phase, template.task_description, 
                            "Checked" if state_item.is_checked else "Pending", state_item.updated_at
                        ])
                else:
                    writer.writerow(["No gatekeeper checklists initialized."])
                writer.writerow([])
                
                # --- SECTION 9: SRS & PROJECT DOCUMENTS ---
                writer.writerow(["=== SRS & PROJECT DOCUMENTS ==="])
                writer.writerow([
                    "Document ID", "Title", "Version", "File URL / Path", "Approval Status", "Approved By", "Uploaded At"
                ])
                if srs_docs:
                    for doc in srs_docs:
                        writer.writerow([
                            doc.id, doc.document_title, doc.version, doc.file_url_or_path, doc.status, doc.approved_by, doc.created_at
                        ])
                else:
                    writer.writerow(["No SRS documents linked."])
                
                return output.getvalue()
            except Exception as e:
                return self._handle_error("export_project_csv_data", e, context={"project_id": project_id})

    def export_project_xlsx_data(self, project_id: str) -> Optional[bytes]:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        import io
        from datetime import datetime, date

        def fmt_dt(val) -> str:
            if not val:
                return "N/A"
            if isinstance(val, str):
                return val
            try:
                return val.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                return str(val)

        def fmt_date(val) -> str:
            if not val:
                return "N/A"
            if isinstance(val, str):
                return val
            try:
                return val.strftime("%Y-%m-%d")
            except Exception:
                return str(val)
        
        with self.SessionLocal() as session:
            try:
                # 1. Fetch core project details
                proj = session.query(Projects).filter_by(id=project_id).first()
                if not proj:
                    return None
                
                # Fetch related data
                # Assignments
                assignments = session.query(ProjectAssignments, Employees, Departments_Roles).join(
                    Employees, ProjectAssignments.employee_id == Employees.id
                ).outerjoin(
                    Departments_Roles, Employees.role_id == Departments_Roles.id
                ).filter(ProjectAssignments.project_id == project_id).all()
                
                # Timeline
                timeline = session.query(ProjectTimeline).filter_by(project_id=project_id).order_by(ProjectTimeline.expected_start).all()
                
                # Payments
                payments = session.query(ProjectPayments).filter_by(project_id=project_id).order_by(ProjectPayments.payment_date.desc()).all()
                
                # Expenses
                expenses = session.query(ProjectExpenses).filter_by(project_id=project_id).order_by(ProjectExpenses.expense_date.desc()).all()
                
                # Developer Tasks
                dev_tasks = session.query(DeveloperTasks, Employees).join(
                    Employees, DeveloperTasks.employee_id == Employees.id
                ).filter(DeveloperTasks.project_id == project_id).order_by(DeveloperTasks.date.desc()).all()
                
                # Content Creator Tasks
                content_tasks = session.query(ContentCreatorTasks, Employees).join(
                    Employees, ContentCreatorTasks.employee_id == Employees.id
                ).filter(ContentCreatorTasks.project_id == project_id).order_by(ContentCreatorTasks.date.desc()).all()
                
                # Checklist items
                checklists = session.query(ProjectChecklistState, ChecklistTemplate).join(
                    ChecklistTemplate, ProjectChecklistState.checklist_id == ChecklistTemplate.id
                ).filter(ProjectChecklistState.project_id == project_id).all()
                
                # SRS
                srs_docs = session.query(SRS_Documents).filter_by(project_id=project_id).order_by(SRS_Documents.created_at.desc()).all()

                # Build openpyxl Workbook
                wb = Workbook()
                # Remove default sheet
                default_sheet = wb.active
                wb.remove(default_sheet)

                # Styles
                header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
                header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid") # brand indigo
                header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                
                data_font = Font(name="Calibri", size=11)
                italic_font = Font(name="Calibri", size=11, italic=True, color="7F7F7F")
                
                border_thin = Side(border_style="thin", color="D1D5DB")
                cell_border = Border(left=border_thin, right=border_thin, top=border_thin, bottom=border_thin)

                left_align = Alignment(horizontal="left", vertical="center")
                center_align = Alignment(horizontal="center", vertical="center")
                right_align = Alignment(horizontal="right", vertical="center")

                # Helper to write sheet
                def write_sheet(title: str, headers: List[str], rows: List[List[Any]], column_alignments: List[Alignment] = None, numeric_formats: Dict[int, str] = None):
                    ws = wb.create_sheet(title=title)
                    ws.views.sheetView[0].showGridLines = True
                    
                    # Write Headers
                    ws.append(headers)
                    for col_num in range(1, len(headers) + 1):
                        cell = ws.cell(row=1, column=col_num)
                        cell.font = header_font
                        cell.fill = header_fill
                        cell.alignment = header_alignment
                        cell.border = cell_border
                    
                    # Write Data
                    if rows:
                        for r_idx, row in enumerate(rows, start=2):
                            ws.append(row)
                            for col_idx, val in enumerate(row, start=1):
                                cell = ws.cell(row=r_idx, column=col_idx)
                                cell.font = data_font
                                cell.border = cell_border
                                
                                # Alignments
                                if column_alignments and col_idx - 1 < len(column_alignments):
                                    cell.alignment = column_alignments[col_idx - 1]
                                else:
                                    cell.alignment = left_align
                                    
                                # Number Formats
                                if numeric_formats and (col_idx - 1) in numeric_formats:
                                    cell.number_format = numeric_formats[col_idx - 1]
                    else:
                        # Write standard placeholder
                        placeholder = ["No recorded database entries for this section."] + [""] * (len(headers) - 1)
                        ws.append(placeholder)
                        for col_idx in range(1, len(headers) + 1):
                            cell = ws.cell(row=2, column=col_idx)
                            cell.font = italic_font
                            cell.border = cell_border
                            cell.alignment = left_align
                    
                    # Adjust column widths
                    for col in ws.columns:
                        max_len = 0
                        for cell in col:
                            if cell.value:
                                val_str = str(cell.value)
                                if len(val_str) > max_len:
                                    max_len = len(val_str)
                        col_letter = get_column_letter(col[0].column)
                        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

                # 1. Project Metadata
                proj_headers = [
                    "Project ID", "Project Name", "Project Type", "Description", "Status",
                    "Client Cost", "Budget", "Approx Cost", "Cost Type", "Start Date",
                    "End Date", "Progress", "Manager", "Client Name", "Team", 
                    "Referred By", "Filled By", "Assigned To", "Created At", "Updated At"
                ]
                # Format Dates/Times
                start_date_str = fmt_date(proj.start_date)
                end_date_str = fmt_date(proj.end_date)
                created_at_str = fmt_dt(proj.created_at)
                updated_at_str = fmt_dt(proj.updated_at)
                
                proj_rows = [[
                    proj.id, proj.name, proj.project_type, proj.description or "N/A", proj.status,
                    proj.client_cost or 0.0, proj.budget or 0.0, proj.approx_cost or 0.0, proj.cost_type or "N/A", start_date_str,
                    end_date_str, f"{self._calculate_project_progress(session, proj)}%", proj.manager or "N/A", proj.client or "N/A", proj.team or "N/A",
                    proj.referred_by or "N/A", proj.filled_by or "N/A", proj.assigned_to or "N/A", created_at_str, updated_at_str
                ]]
                
                # Alignments: ID(C), Name(L), Type(C), Desc(L), Status(C), ClientCost(R), Budget(R), ApproxCost(R), CostType(C), Dates(C), Progress(C), etc.
                proj_alignments = [
                    center_align, left_align, center_align, left_align, center_align,
                    right_align, right_align, right_align, center_align, center_align,
                    center_align, center_align, left_align, left_align, left_align,
                    left_align, left_align, left_align, center_align, center_align
                ]
                # Numeric Formats: Client Cost (index 5), Budget (index 6), Approx Cost (index 7)
                proj_formats = {5: "₹#,##0.00", 6: "₹#,##0.00", 7: "₹#,##0.00"}
                
                write_sheet("Project Metadata", proj_headers, proj_rows, proj_alignments, proj_formats)

                # 2. Assigned Team Members
                team_headers = [
                    "Employee ID", "Full Name", "Email", "Role/Job Title", 
                    "Standard Cost Rate", "Standard Billing Rate", "Custom Cost Override", "Custom Billing Override", "Assigned At"
                ]
                team_rows = []
                for assign, emp, role in assignments:
                    assigned_str = fmt_dt(assign.assigned_at)
                    team_rows.append([
                        emp.id, emp.full_name, emp.email, role.role_name if role else "Employee",
                        emp.hourly_cost_rate or 0.0, emp.hourly_billing_rate or 0.0, assign.custom_hourly_cost, assign.custom_hourly_billing, assigned_str
                    ])
                team_alignments = [
                    center_align, left_align, left_align, left_align,
                    right_align, right_align, right_align, right_align, center_align
                ]
                team_formats = {4: "₹#,##0.00", 5: "₹#,##0.00", 6: "₹#,##0.00", 7: "₹#,##0.00"}
                
                write_sheet("Assigned Team Members", team_headers, team_rows, team_alignments, team_formats)

                # 3. Timeline & Milestones
                timeline_headers = [
                    "Milestone ID", "Milestone Name", "Expected Start", "Expected End", 
                    "Actual Start", "Actual End", "Status", "Remarks", "Created At"
                ]
                timeline_rows = []
                for t in timeline:
                    exp_start = fmt_date(t.expected_start)
                    exp_end = fmt_date(t.expected_end)
                    act_start = fmt_date(t.actual_start)
                    act_end = fmt_date(t.actual_end)
                    created_at = fmt_dt(t.created_at)
                    timeline_rows.append([
                        t.id, t.milestone_name, exp_start, exp_end,
                        act_start, act_end, t.status, t.remarks or "N/A", created_at
                    ])
                timeline_alignments = [
                    center_align, left_align, center_align, center_align,
                    center_align, center_align, center_align, left_align, center_align
                ]
                
                write_sheet("Timeline & Milestones", timeline_headers, timeline_rows, timeline_alignments)

                # 4. Payments
                payment_headers = [
                    "Payment ID", "Amount", "Payment Date", "Payment Method", "Reference Number", "Remarks", "Logged At"
                ]
                payment_rows = []
                for p in payments:
                    pay_date = fmt_date(p.payment_date)
                    created_at = fmt_dt(p.created_at)
                    payment_rows.append([
                        p.id, p.amount or 0.0, pay_date, p.payment_method or "N/A", p.reference_number or "N/A", p.remarks or "N/A", created_at
                    ])
                payment_alignments = [
                    center_align, right_align, center_align, center_align, center_align, left_align, center_align
                ]
                payment_formats = {1: "₹#,##0.00"}
                
                write_sheet("Payments", payment_headers, payment_rows, payment_alignments, payment_formats)

                # 5. Expenses
                expense_headers = [
                    "Expense ID", "Expense Name", "Amount", "Expense Date", "Description", "Logged At"
                ]
                expense_rows = []
                for e in expenses:
                    exp_date = fmt_date(e.expense_date)
                    created_at = fmt_dt(e.created_at)
                    expense_rows.append([
                        e.id, e.expense_name, e.amount or 0.0, exp_date, e.description or "N/A", created_at
                    ])
                expense_alignments = [
                    center_align, left_align, right_align, center_align, left_align, center_align
                ]
                expense_formats = {2: "₹#,##0.00"}
                
                write_sheet("Expenses", expense_headers, expense_rows, expense_alignments, expense_formats)

                # 6. Developer Timesheets
                dev_headers = [
                    "Task ID", "Employee Name", "Date Logged", "Hours Logged", "Tech Stack Used", 
                    "GitHub Link", "Task Performed", "Tomorrow's Plan", "Employee Cost", "Billing Amount", "Profit/Loss", "Logged At"
                ]
                dev_rows = []
                for dt, emp in dev_tasks:
                    dt_date = fmt_date(dt.date)
                    created_at = fmt_dt(dt.created_at)
                    dev_rows.append([
                        dt.id, emp.full_name, dt_date, dt.hours_logged or 0.0, dt.tech_stack or "N/A",
                        dt.github_link or "N/A", dt.task_performed or "N/A", dt.tomorrow_plan or "N/A",
                        dt.employee_cost or 0.0, dt.billing_amount or 0.0, dt.profit_loss or 0.0, created_at
                    ])
                dev_alignments = [
                    center_align, left_align, center_align, right_align, center_align,
                    left_align, left_align, left_align, right_align, right_align, right_align, center_align
                ]
                dev_formats = {3: "0.0", 8: "₹#,##0.00", 9: "₹#,##0.00", 10: "₹#,##0.00"}
                
                write_sheet("Developer Timesheets", dev_headers, dev_rows, dev_alignments, dev_formats)

                # 7. Content Creator Timesheets
                content_headers = [
                    "Task ID", "Employee Name", "Date Logged", "Hours Logged", "Reels Count", "Long Video Count",
                    "Poster Count", "Calls Made", "Platform", "Total Content", "Task Performed", 
                    "Employee Cost", "Billing Amount", "Profit/Loss", "Logged At"
                ]
                content_rows = []
                for ct, emp in content_tasks:
                    ct_date = fmt_date(ct.date)
                    created_at = fmt_dt(ct.created_at)
                    content_rows.append([
                        ct.id, emp.full_name, ct_date, ct.hours_logged or 0.0, ct.reels_count or 0, ct.long_video_count or 0,
                        ct.poster_count or 0, ct.calls_made or 0, ct.platform or "N/A", ct.total_content or 0, ct.task_performed or "N/A",
                        ct.employee_cost or 0.0, ct.billing_amount or 0.0, ct.profit_loss or 0.0, created_at
                    ])
                content_alignments = [
                    center_align, left_align, center_align, right_align, right_align, right_align,
                    right_align, right_align, center_align, right_align, left_align,
                    right_align, right_align, right_align, center_align
                ]
                content_formats = {3: "0.0", 4: "#,##0", 5: "#,##0", 6: "#,##0", 7: "#,##0", 9: "#,##0", 11: "₹#,##0.00", 12: "₹#,##0.00", 13: "₹#,##0.00"}
                
                write_sheet("Content Creator Timesheets", content_headers, content_rows, content_alignments, content_formats)

                # 8. Gatekeeper Checklist
                checklist_headers = [
                    "Checklist Item ID", "Phase", "Task Description", "Completed State", "Last Updated"
                ]
                checklist_rows = []
                for state_item, template in checklists:
                    updated_at = fmt_dt(state_item.updated_at)
                    checklist_rows.append([
                        state_item.id, template.phase, template.task_description,
                        "Checked" if state_item.is_checked else "Pending", updated_at
                    ])
                checklist_alignments = [
                    center_align, center_align, left_align, center_align, center_align
                ]
                
                write_sheet("Gatekeeper Checklist", checklist_headers, checklist_rows, checklist_alignments)

                # 9. SRS & Documents
                srs_headers = [
                    "Document ID", "Title", "Version", "File URL / Path", "Approval Status", "Approved By", "Uploaded At"
                ]
                srs_rows = []
                for doc in srs_docs:
                    created_at = fmt_dt(doc.created_at)
                    srs_rows.append([
                        doc.id, doc.document_title, doc.version, doc.file_url_or_path or "N/A", doc.status, doc.approved_by or "N/A", created_at
                    ])
                srs_alignments = [
                    center_align, left_align, center_align, left_align, center_align, left_align, center_align
                ]
                
                write_sheet("SRS & Documents", srs_headers, srs_rows, srs_alignments)

                # Save Workbook to binary stream
                out = io.BytesIO()
                wb.save(out)
                return out.getvalue()
                
            except Exception as e:
                return self._handle_error("export_project_xlsx_data", e, context={"project_id": project_id})

    def _is_checklist_completed(self, session, project_id: str, phase: str) -> bool:
        templates = session.query(ChecklistTemplate).filter_by(project_id=project_id, phase=phase).all()
        if not templates:
            return True
        template_ids = [t.id for t in templates]
        checked_count = session.query(ProjectChecklistState).filter(
            ProjectChecklistState.project_id == project_id,
            ProjectChecklistState.checklist_id.in_(template_ids),
            ProjectChecklistState.is_checked == True
        ).count()
        return checked_count == len(templates)

    def edit_project(self, project_id: str, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                proj = session.query(Projects).filter_by(id=project_id).first()
                if not proj:
                    return json.dumps({"error": "Project not found"})
                
                # Check status transition rules
                if "status" in data:
                    new_status = data["status"]
                    if new_status == "In Progress" and proj.status != "In Progress":
                        if not self._is_checklist_completed(session, project_id, "START"):
                            return json.dumps({"error": "Cannot start project. The 'START' phase checklist must be fully completed first."})
                    elif new_status == "Completed" and proj.status != "Completed":
                        if not self._is_checklist_completed(session, project_id, "END"):
                            return json.dumps({"error": "Cannot complete project. The 'END' phase checklist must be fully completed first."})

                for key, value in data.items():
                    if hasattr(proj, key):
                        setattr(proj, key, value)
                session.commit()
                session.refresh(proj)
                return json.dumps(self.model_to_dict(proj), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("edit_project", e, context={"project_id": project_id})

    def delete_project(self, project_id: str) -> str:

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

                # Delete all payment records
                session.query(ProjectPayments).filter_by(project_id=project_id).delete()

                session.delete(proj)
                session.commit()
                return json.dumps({"message": "Project and all associated data deleted successfully"})
            except Exception as e:
                session.rollback()
                return self._handle_error("delete_project", e)

    def add_project_expense(self, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                expense = ProjectExpenses(**data)
                session.add(expense)
                session.commit()
                session.refresh(expense)
                return json.dumps(self.model_to_dict(expense), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("add_project_expense", e, context=data)

    def get_project_expenses(self, project_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                expenses = session.query(ProjectExpenses).filter_by(project_id=project_id).all()
                return json.dumps([self.model_to_dict(e) for e in expenses], indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_project_expenses", e)

    def delete_project_expense(self, expense_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                expense = session.query(ProjectExpenses).filter_by(id=expense_id).first()
                if not expense:
                    return json.dumps({"error": f"Expense not found."})
                session.delete(expense)
                session.commit()
                return json.dumps({"message": f"Expense deleted."})
            except Exception as e:
                session.rollback()
                return self._handle_error("delete_project_expense", e)

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

    def edit_project_timeline(self, timeline_id: str, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                timeline = session.query(ProjectTimeline).filter_by(id=timeline_id).first()
                if not timeline:
                    return json.dumps({"error": "Timeline milestone not found"})
                for key, value in data.items():
                    setattr(timeline, key, value)
                
                session.flush()
                # Auto-update project progress
                project_id = timeline.project_id
                total = session.query(func.count(ProjectTimeline.id)).filter_by(project_id=project_id).scalar()
                if total and total > 0:
                    completed = session.query(func.count(ProjectTimeline.id)).filter(
                        ProjectTimeline.project_id == project_id,
                        ProjectTimeline.status.ilike('%completed%')
                    ).scalar()
                    proj = session.query(Projects).filter_by(id=project_id).first()
                    if proj:
                        proj.progress = f"{int((completed / total) * 100)}%"

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
                
                project_id = timeline.project_id
                session.delete(timeline)
                session.flush()
                
                # Auto-update project progress
                total = session.query(func.count(ProjectTimeline.id)).filter_by(project_id=project_id).scalar()
                proj = session.query(Projects).filter_by(id=project_id).first()
                if proj:
                    if total and total > 0:
                        completed = session.query(func.count(ProjectTimeline.id)).filter(
                            ProjectTimeline.project_id == project_id,
                            ProjectTimeline.status.ilike('%completed%')
                        ).scalar()
                        proj.progress = f"{int((completed / total) * 100)}%"
                    else:
                        proj.progress = "0%"

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

    # ==========================================
    #             ATTENDANCE & LEAVES
    # ==========================================
    def check_in(self, employee_id: str, ip_address: str = None) -> str:
        with self.SessionLocal() as session:
            try:
                now = datetime.now()
                start_of_day = datetime.combine(now.date(), datetime.min.time())
                end_of_day = datetime.combine(now.date(), datetime.max.time())
                # Check if already checked in today
                existing = session.query(Attendance).filter(
                    Attendance.employee_id == employee_id,
                    Attendance.date.between(start_of_day, end_of_day)
                ).first()
                
                if existing:
                    return json.dumps({"error": "Already checked in for today."})
                
                new_attendance = Attendance(
                    employee_id=employee_id,
                    check_in_time=datetime.now(),
                    date=datetime.now(),
                    status="Present",
                    ip_address=ip_address
                )

                employee = session.query(Employees).filter_by(id=employee_id).first()
                if not employee:
                    return json.dumps({"error": "Employee not found."})
                employee_name = employee.full_name
                session.add(new_attendance)
                session.commit()
                session.refresh(new_attendance)
                attendence_dict = self.model_to_dict(new_attendance)
                attendence_dict['employee_name']=employee_name
                return json.dumps(attendence_dict, indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("check_in", e)

    def check_out(self, employee_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                now = datetime.now()
                start_of_day = datetime.combine(now.date(), datetime.min.time())
                end_of_day = datetime.combine(now.date(), datetime.max.time())
                attendance = session.query(Attendance).filter(
                    Attendance.employee_id == employee_id,
                    Attendance.date.between(start_of_day, end_of_day)
                ).first()
                
                if not attendance:
                    return json.dumps({"error": "No check-in record found for today."})
                
                if attendance.check_out_time:
                    return json.dumps({"error": "Already checked out for today."})
                
                attendance.check_out_time = datetime.now()
                attendance.status = "Checked Out"
                # Calculate total hours
                time_diff = attendance.check_out_time - attendance.check_in_time
                attendance.total_hours = time_diff.total_seconds() / 3600.0

                session.commit()
                session.refresh(attendance)
                return json.dumps(self.model_to_dict(attendance), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("check_out", e)

    def record_daily_absences_internal(self, session) -> None:
        """Helper to dynamically populate 'Absent' records for active employees who haven't checked in today."""
        now = datetime.now()
        start_of_day = datetime.combine(now.date(), datetime.min.time())
        end_of_day = datetime.combine(now.date(), datetime.max.time())
        
        active_employees = session.query(Employees).filter(Employees.is_active == True).all()
        for emp in active_employees:
            # Check if there is any attendance record for this employee today
            existing = session.query(Attendance).filter(
                Attendance.employee_id == emp.id,
                Attendance.date.between(start_of_day, end_of_day)
            ).first()
            
            if not existing:
                absent_record = Attendance(
                    employee_id=emp.id,
                    date=now,
                    status="Absent",
                    total_hours=0.0,
                    notes="Auto-recorded absent (no check-in detected)"
                )
                session.add(absent_record)
        session.commit()

    def record_daily_absences(self) -> str:
        with self.SessionLocal() as session:
            try:
                self.record_daily_absences_internal(session)
                return json.dumps({"status": "success", "message": "Daily absences recorded successfully."})
            except Exception as e:
                session.rollback()
                return self._handle_error("record_daily_absences", e)

    def get_all_attendance(self) -> str:
        with self.SessionLocal() as session:
            try:
                # Automatically record absences first!
                self.record_daily_absences_internal(session)
                
                # Fetch all attendance records joined with Employees to resolve names
                records = session.query(Attendance, Employees.full_name)\
                                 .join(Employees, Attendance.employee_id == Employees.id)\
                                 .order_by(Attendance.date.desc())\
                                 .all()
                
                results = []
                for r, name in records:
                    d = self.model_to_dict(r)
                    d['employee_name'] = name
                    results.append(d)
                return json.dumps(results, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_all_attendance", e)

    # ==========================================
    #          PROJECT PAYMENTS
    # ==========================================

    def add_project_payment(self, data: dict) -> str:
        with self.SessionLocal() as session:
            try:
                new_payment = ProjectPayments(**data)
                session.add(new_payment)
                session.commit()
                session.refresh(new_payment)
                return json.dumps(self.model_to_dict(new_payment), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("add_project_payment", e, context=data)

    def get_project_payments(self, project_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                payments = session.query(ProjectPayments).filter_by(project_id=project_id).order_by(ProjectPayments.payment_date.desc()).all()
                return json.dumps([self.model_to_dict(p) for p in payments], indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_project_payments", e, context={"project_id": project_id})

    def delete_project_payment(self, payment_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                payment = session.query(ProjectPayments).filter_by(id=payment_id).first()
                if not payment:
                    return json.dumps({"error": "Payment record not found."})
                session.delete(payment)
                session.commit()
                return json.dumps({"message": "Payment record deleted successfully."})
            except Exception as e:
                session.rollback()
                return self._handle_error("delete_project_payment", e, context={"payment_id": payment_id})

    def get_employee_attendance(self, employee_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                records = session.query(Attendance).filter_by(employee_id=employee_id).all()
                return json.dumps([self.model_to_dict(r) for r in records], indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_employee_attendance", e)

    def get_all_login_history(self) -> str:
        with self.SessionLocal() as session:
            try:
                records = session.query(LoginHistory).order_by(LoginHistory.login_timestamp.desc()).all()
                
                # Fetch all employees and admins to build a fast map for metadata resolution
                employees = session.query(Employees.id, Employees.full_name, Employees.username).all()
                admins = session.query(Admins.id, Admins.full_name, Admins.username).all()
                
                user_map = {}
                for e_id, name, uname in employees:
                    user_map[e_id] = {"full_name": name, "username": uname}
                for a_id, name, uname in admins:
                    user_map[a_id] = {"full_name": name, "username": uname}
                
                results = []
                for r in records:
                    r_dict = self.model_to_dict(r)
                    
                    # Parse user agent into device/browser
                    ua = r.user_agent or "Unknown"
                    browser, device = self.parse_user_agent(ua)
                    
                    # Resolve names
                    user_info = user_map.get(r.user_id, {"full_name": "Unknown", "username": "N/A"})
                    r_dict["full_name"] = user_info["full_name"]
                    r_dict["username"] = user_info["username"]
                    r_dict["browser"] = browser
                    r_dict["device"] = device
                    
                    # Format login_timestamp as ISO-8601 string ending with Z (UTC indicator)
                    if isinstance(r.login_timestamp, datetime):
                        r_dict["login_timestamp"] = r.login_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
                    
                    results.append(r_dict)
                    
                return json.dumps(results, indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_all_login_history", e)

    def get_all_leave_requests(self) -> str:
        with self.SessionLocal() as session:
            try:
                records = session.query(LeaveRequest).all()
                return json.dumps([self.model_to_dict(r) for r in records], indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_all_leave_requests", e)

    def create_leave_request(self, employee_id: str, start_date: str, end_date: str, reason: str) -> str:
        with self.SessionLocal() as session:
            try:
                if isinstance(start_date, str):
                    start_date = datetime.strptime(start_date, "%Y-%m-%d")
                if isinstance(end_date, str):
                    end_date = datetime.strptime(end_date, "%Y-%m-%d")
                    
                new_request = LeaveRequest(
                    employee_id=employee_id,
                    start_date=start_date,
                    end_date=end_date,
                    reason=reason,
                    status="Pending"
                )
                session.add(new_request)
                session.commit()
                session.refresh(new_request)
                return json.dumps(self.model_to_dict(new_request), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("create_leave_request", e)

    def get_employee_leave_requests(self, employee_id: str) -> str:
        with self.SessionLocal() as session:
            try:
                records = session.query(LeaveRequest).filter_by(employee_id=employee_id).all()
                return json.dumps([self.model_to_dict(r) for r in records], indent=4, default=str)
            except Exception as e:
                return self._handle_error("get_employee_leave_requests", e)

    def update_leave_request_status(self, leave_id: str, status: str) -> str:
        with self.SessionLocal() as session:
            try:
                record = session.query(LeaveRequest).filter_by(id=leave_id).first()
                if not record:
                    return json.dumps({"error": "Leave request not found."})
                record.status = status
                session.commit()
                session.refresh(record)
                return json.dumps(self.model_to_dict(record), indent=4, default=str)
            except Exception as e:
                session.rollback()
                return self._handle_error("update_leave_request_status", e)








































