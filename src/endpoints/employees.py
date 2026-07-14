from fastapi import APIRouter, Depends, HTTPException
import logging
from schemas import (
    EmployeeCreate, EmployeeUpdate, 
    AdminCreate, AdminUpdate, 
    DepartmentRoleCreate, DepartmentRoleUpdate
)
from src.database.database_operations import DatabaseOperations
from src.database.database_create import SessionLocal
from src.database.database_tables import Admins
from src.endpoints.auth import get_current_user, handle_response

logger = logging.getLogger("Yana_Employees_Router")
router = APIRouter(prefix="", tags=["Organization Management"])
db = DatabaseOperations()

# ==========================================
#        EMPLOYEE PROFILE ENDPOINTS
# ==========================================

@router.post("/employees/create", tags=["Employees"])
def create_employee(employee: EmployeeCreate, current_user: dict = Depends(get_current_user)):
    try:
        data = employee.model_dump(exclude_unset=True)
        response = db.add_employee(data)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in create_employee: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process employee creation request.")

@router.get("/employees/all", tags=["Employees"])
def get_all_employees(current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_all_employees()
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_all_employees: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch employees.")

@router.get("/employees/get/{employee_id}", tags=["Employees"])
def get_employee(employee_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_employee(employee_id)
        data = handle_response(response)
        
        # RBAC: Strip financial data for ManagerAdmins
        if current_user.get("access_level") == "ManagerAdmin" and isinstance(data, dict):
            data.pop("salary", None)
            data.pop("hourly_cost_rate", None)
            data.pop("hourly_billing_rate", None)
            
        return data
    except Exception as e:
        logger.error(f"Router Error in get_employee: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch employee details.")

@router.put("/employees/update/{employee_id}", tags=["Employees"])
def update_employee(employee_id: str, employee: EmployeeUpdate, current_user: dict = Depends(get_current_user)):
    try:
        data = employee.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No valid data provided to update.")

        # General Profile Field Validations
        import re
        from datetime import datetime, date

        # 1. Full Legal Name
        if "full_name" in data and data["full_name"]:
            name = str(data["full_name"]).strip()
            if not (3 <= len(name) <= 60):
                raise HTTPException(status_code=400, detail="Full Legal Name must be between 3 and 60 characters.")
            if not re.match(r"^[a-zA-Z\s]+$", name):
                raise HTTPException(status_code=400, detail="Full Legal Name must contain only alphabets and spaces.")

        # 2. Date of Birth
        parsed_dob = None
        if "date_of_birth" in data and data["date_of_birth"] and data["date_of_birth"] != "N/A":
            dob_val = data["date_of_birth"]
            parsed_dob = db._parse_datetime(dob_val)
            if not parsed_dob:
                raise HTTPException(status_code=400, detail="Invalid Date of Birth format.")
            today = date.today()
            age = today.year - parsed_dob.year - ((today.month, today.day) < (parsed_dob.month, parsed_dob.day))
            if age < 18:
                raise HTTPException(status_code=400, detail="Employee age must be minimum 18 years.")

        # 3. Gender
        if "gender" in data and data["gender"]:
            if data["gender"] not in ["Male", "Female", "Other", "N/A"]:
                raise HTTPException(status_code=400, detail="Gender must be one of: Male, Female, Other, N/A.")

        # 4. Primary Phone
        if "contact_number" in data and data["contact_number"]:
            phone = str(data["contact_number"]).strip()
            if not phone.isdigit() or len(phone) != 12:
                raise HTTPException(status_code=400, detail="Primary Phone must contain exactly 12 digits.")

        # 5. Date of Joining
        if "date_of_joining" in data and data["date_of_joining"] and data["date_of_joining"] != "N/A":
            doj_val = data["date_of_joining"]
            parsed_doj = db._parse_datetime(doj_val)
            if not parsed_doj:
                raise HTTPException(status_code=400, detail="Invalid Date of Joining format.")
            if parsed_doj.date() > date.today():
                raise HTTPException(status_code=400, detail="Date of Joining cannot be in the future.")
            
            # Fetch DOB if not updated in this request
            dob_to_check = parsed_dob
            if not dob_to_check:
                with SessionLocal() as session:
                    from src.database.database_tables import Employees
                    emp_record = session.query(Employees).filter(Employees.id == employee_id).first()
                    if emp_record and emp_record.date_of_birth and emp_record.date_of_birth != "N/A":
                        dob_to_check = db._parse_datetime(emp_record.date_of_birth)
            
            if dob_to_check:
                try:
                    dob_plus_18 = dob_to_check.replace(year=dob_to_check.year + 18)
                except ValueError:
                    dob_plus_18 = dob_to_check.replace(year=dob_to_check.year + 18, day=28)
                if parsed_doj.date() < dob_plus_18.date():
                    raise HTTPException(status_code=400, detail="Date of Joining cannot be before Date of Birth + 18 years.")

        # 6. Reporting Manager
        if "reporting_manager" in data and data["reporting_manager"] and data["reporting_manager"] != "N/A":
            manager_val = str(data["reporting_manager"]).strip()
            with SessionLocal() as session:
                from src.database.database_tables import Employees
                mgr_exists = session.query(Employees).filter(
                    (Employees.id == manager_val) | 
                    (Employees.username == manager_val) | 
                    (Employees.full_name == manager_val)
                ).first()
                if not mgr_exists:
                    raise HTTPException(status_code=400, detail="Reporting Manager must be an existing employee in the system.")

        # 7. Highest Qualification
        if "highest_qualification" in data and data["highest_qualification"]:
            if data["highest_qualification"] not in ["10th", "12th", "Diploma", "Graduate", "Post Graduate", "PhD", "N/A"]:
                raise HTTPException(status_code=400, detail="Highest Qualification must be one of: 10th, 12th, Diploma, Graduate, Post Graduate, PhD, N/A.")

        # 8. Total Experience
        if "experience" in data and data["experience"] is not None and str(data["experience"]).strip() != "N/A":
            exp_str = str(data["experience"]).strip()
            try:
                exp_float = float(exp_str)
                if not (0 <= exp_float <= 50):
                    raise HTTPException(status_code=400, detail="Total Experience must be between 0 and 50 years.")
            except ValueError:
                raise HTTPException(status_code=400, detail="Total Experience must be a valid number.")

        # 9. Previous Employer / Job Role conditional validation
        exp_val = None
        if "experience" in data and data["experience"] is not None and str(data["experience"]).strip() != "N/A":
            try:
                exp_val = float(data["experience"])
            except ValueError:
                pass
        else:
            with SessionLocal() as session:
                from src.database.database_tables import Employees
                emp_rec = session.query(Employees).filter(Employees.id == employee_id).first()
                if emp_rec and emp_rec.experience and emp_rec.experience != "N/A":
                    try:
                        exp_val = float(emp_rec.experience)
                    except ValueError:
                        pass

        if exp_val and exp_val > 0:
            # Previous Employer
            prev_emp = data.get("previous_employer")
            if prev_emp is None:
                with SessionLocal() as session:
                    from src.database.database_tables import Employees
                    emp_rec = session.query(Employees).filter(Employees.id == employee_id).first()
                    if emp_rec:
                        prev_emp = emp_rec.previous_employer
            if not prev_emp or str(prev_emp).strip() == "N/A" or len(str(prev_emp).strip()) < 2:
                raise HTTPException(status_code=400, detail="Previous Employer is required and must be at least 2 characters if experience > 0.")

            # Previous Job Role
            prev_role = data.get("previous_job_role")
            if prev_role is None:
                with SessionLocal() as session:
                    from src.database.database_tables import Employees
                    emp_rec = session.query(Employees).filter(Employees.id == employee_id).first()
                    if emp_rec:
                        prev_role = emp_rec.previous_job_role
            if not prev_role or str(prev_role).strip() == "N/A" or len(str(prev_role).strip()) < 2:
                raise HTTPException(status_code=400, detail="Previous Job Role is required and must be at least 2 characters if experience > 0.")

        # 10. Skills Constraints
        if "skills" in data and data["skills"]:
            import json
            skills_val = data["skills"]
            skills_list = []
            try:
                if isinstance(skills_val, str):
                    if skills_val.startswith("["):
                        skills_list = json.loads(skills_val)
                    else:
                        skills_list = [s.strip() for s in skills_val.split(",") if s.strip()]
                elif isinstance(skills_val, list):
                    skills_list = skills_val
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid skills format.")
            
            seen_skills = set()
            for s in skills_list:
                s_clean = str(s).strip().lower()
                if s_clean in seen_skills:
                    raise HTTPException(status_code=400, detail="Skills cannot contain duplicates.")
                seen_skills.add(s_clean)
                if len(str(s).strip()) > 30:
                    raise HTTPException(status_code=400, detail="Each skill must be at most 30 characters.")
            
            if len(skills_list) > 15:
                raise HTTPException(status_code=400, detail="Skills count cannot exceed 15 skills.")

        # 11. Resume / Portfolio Link
        if "resume" in data and data["resume"] and data["resume"] != "N/A":
            res_link = str(data["resume"]).strip()
            if not (res_link.startswith("http://") or res_link.startswith("https://")):
                raise HTTPException(status_code=400, detail="Resume / Portfolio Link must be a valid URL starting with http:// or https://")

        # 12. Bank Account Number
        if "bank_account" in data and data["bank_account"] and data["bank_account"] != "N/A":
            acc = str(data["bank_account"]).strip()
            if not acc.isdigit() or not (9 <= len(acc) <= 18):
                raise HTTPException(status_code=400, detail="Bank Account Number must contain only digits and be between 9 and 18 digits.")

        # 13. IFSC Code
        if "ifsc_code" in data and data["ifsc_code"] and data["ifsc_code"] != "N/A":
            ifsc = str(data["ifsc_code"]).strip().upper()
            if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", ifsc):
                raise HTTPException(status_code=400, detail="Invalid IFSC Code format. E.g. HDFC0001234")
            data["ifsc_code"] = ifsc

        # 14. UPI ID
        if "upi_id" in data and data["upi_id"] and data["upi_id"] != "N/A":
            upi = str(data["upi_id"]).strip()
            if "@" not in upi:
                raise HTTPException(status_code=400, detail="Invalid UPI ID. Must contain '@'")

        # 15. PAN Number
        if "pan_number" in data and data["pan_number"] and data["pan_number"] != "N/A":
            pan = str(data["pan_number"]).strip().upper()
            if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", pan):
                raise HTTPException(status_code=400, detail="Invalid PAN Number format. E.g. ABCDE1234F")
            data["pan_number"] = pan

        # 16. Aadhaar Number
        adh_key = "adhar_number" if "adhar_number" in data else ("aadhaar_number" if "aadhaar_number" in data else None)
        if adh_key and data[adh_key] and data[adh_key] != "N/A":
            adh = str(data[adh_key]).strip()
            if not adh.isdigit() or len(adh) != 12:
                raise HTTPException(status_code=400, detail="Aadhaar Number must contain exactly 12 digits.")

        # 17. Emergency Contact
        if "emergency_contact" in data and data["emergency_contact"] and data["emergency_contact"] != "N/A":
            contact_str = str(data["emergency_contact"]).strip()
            if "-" in contact_str:
                parts = contact_str.split("-", 1)
                name_part = parts[0].strip()
                phone_part = parts[1].strip()
                if not re.match(r"^[a-zA-Z\s]+$", name_part):
                    raise HTTPException(status_code=400, detail="Emergency contact name must contain only alphabets and spaces.")
                if not phone_part.isdigit() or len(phone_part) != 10:
                    raise HTTPException(status_code=400, detail="Emergency contact phone must contain exactly 10 digits.")
            else:
                raise HTTPException(status_code=400, detail="Emergency contact must be in the format 'Name - Phone'.")

        # 18. Relationship
        if "relationship_with_emergency_contact" in data and data["relationship_with_emergency_contact"]:
            rel = str(data["relationship_with_emergency_contact"]).strip()
            if rel not in ["Father", "Mother", "Brother", "Sister", "Spouse", "Friend", "Guardian", "Other", "N/A"]:
                raise HTTPException(status_code=400, detail="Relationship with Emergency Contact must be one of: Father, Mother, Brother, Sister, Spouse, Friend, Guardian, Other, N/A.")

        # Enforcement: Employees can only edit their own profile
        if current_user.get("role") == "employee":
            if current_user.get("id") != employee_id:
                raise HTTPException(status_code=403, detail="Access denied. Employees can only update their own profile.")
            
            # Fetch current state from DB for comparison and validation
            from src.database.database_tables import Employees, Departments_Roles
            import json
            
            is_unlocked_session = False
            with SessionLocal() as session:
                current_emp = session.query(Employees).filter(Employees.id == employee_id).first()
                if not current_emp:
                    raise HTTPException(status_code=404, detail="Employee not found.")

                is_unlocked = bool(current_emp.profile_unlocked)
                if is_unlocked and current_emp.profile_unlocked_until:
                    if datetime.utcnow() > current_emp.profile_unlocked_until:
                        current_emp.profile_unlocked = False
                        current_emp.profile_unlocked_until = None
                        session.commit()
                        is_unlocked = False
                is_unlocked_session = is_unlocked

                def clean_val(val):
                    if val is None or val == "" or str(val).strip().upper() == "N/A":
                        return ""
                    return str(val).strip()

                def get_final_val(field):
                    if field in data:
                        return data[field]
                    return getattr(current_emp, field, None)

                # 1. Read-only fields validation (admin controlled)
                if not is_unlocked:
                    read_only_fields = [
                        "date_of_joining", "reporting_manager", "role_id", "is_active", "username",
                        "email", "contact_number", "salary", "hourly_cost_rate", "hourly_billing_rate",
                        "bank_name", "bank_account", "ifsc_code", "upi_id", "account_holder_name",
                        "pf_number", "esic_number", "tax_details", "compliance_verified",
                        "adhar_number", "pan_number"
                    ]
                    for field in read_only_fields:
                        if field in data:
                            db_val = getattr(current_emp, field, None)
                            new_val = data[field]
                            if clean_val(new_val) != clean_val(db_val):
                                raise HTTPException(
                                    status_code=403,
                                    detail=f"Permission Denied: Field '{field}' is HR/Admin controlled and cannot be modified."
                                )

                # 2. Editable once validation (during onboarding)
                if not is_unlocked:
                    editable_once_fields = [
                        "highest_qualification", "specialization", 
                        "full_name", "fathers_name", "date_of_birth", "gender"
                    ]
                    for field in editable_once_fields:
                        if field in data:
                            db_val = getattr(current_emp, field, None)
                            new_val = data[field]
                            db_cleaned = clean_val(db_val)
                            new_cleaned = clean_val(new_val)
                            if db_cleaned != "":
                                if new_cleaned != db_cleaned:
                                    raise HTTPException(
                                        status_code=403,
                                        detail=f"Permission Denied: Field '{field}' has already been set and can only be changed by an Admin."
                                    )

                # 3. Mandatory Fields validation
                mandatory_fields = {
                    "full_name": "Full Legal Name",
                    "date_of_birth": "Date of Birth",
                    "gender": "Gender",
                    "address": "Permanent Address",
                    "contact_number": "Primary Phone",
                    "email": "Primary Email",
                    "emergency_contact": "Emergency Contact Name & Number",
                    "relationship_with_emergency_contact": "Relationship",
                    "date_of_joining": "Date of Joining",
                    "reporting_manager": "Reporting Manager",
                    "highest_qualification": "Highest Qualification"
                }
                for field_name, label in mandatory_fields.items():
                    val = get_final_val(field_name)
                    if clean_val(val) == "":
                        raise HTTPException(
                            status_code=400,
                            detail=f"Validation Error: '{label}' is a mandatory field and cannot be left empty."
                        )

                # Skills count check (Minimum 3 skills)
                skills_val = get_final_val("skills")
                skills_list = []
                if skills_val:
                    try:
                        if isinstance(skills_val, str):
                            if skills_val.startswith("["):
                                skills_list = json.loads(skills_val)
                            else:
                                skills_list = [s.strip() for s in skills_val.split(",") if s.strip()]
                        elif isinstance(skills_val, list):
                            skills_list = skills_val
                    except Exception:
                        pass
                if len(skills_list) < 3:
                    raise HTTPException(
                        status_code=400,
                        detail="Validation Error: Core Skills & Competencies must contain at least 3 skills."
                    )

                # Resume check for technical/design roles
                is_tech_design = False
                if current_emp.role_id:
                    role_record = session.query(Departments_Roles).filter(Departments_Roles.id == current_emp.role_id).first()
                    if role_record:
                        dept_name = (role_record.department_name or "").lower()
                        role_name = (role_record.role_name or "").lower()
                        keywords = ["tech", "dev", "engineer", "design", "it", "qa", "programming", "developer", "software", "ui", "ux", "graphics", "editor"]
                        if any(kw in dept_name or kw in role_name for kw in keywords):
                            is_tech_design = True

                if is_tech_design:
                    resume_val = get_final_val("resume")
                    if clean_val(resume_val) == "":
                        raise HTTPException(
                            status_code=400,
                            detail="Validation Error: Resume / Portfolio Link is mandatory for technical/design roles."
                        )

            if is_unlocked_session:
                data["profile_unlocked"] = False
                data["profile_edit_requested"] = False

        response = db.edit_employee(employee_id, data)
        # Log profile update action in audit logs
        try:
            db.write_audit_log(
                user_id=current_user.get("id") or "Unknown",
                action="profile_update",
                target_id=employee_id,
                details=data
            )
        except Exception as audit_err:
            logger.error(f"Audit log writing failed: {str(audit_err)}")
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in update_employee: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update employee profile.")

@router.delete("/employees/delete/{employee_id}", tags=["Employees"])
def delete_employee(employee_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.delete_employee(employee_id)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in delete_employee: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete employee profile.")


# ==========================================
#        ADMIN MANAGEMENT ENDPOINTS
# ==========================================

@router.post("/admins/create", tags=["Admins"])
def create_admin(admin: AdminCreate, current_user: dict = Depends(get_current_user)):
    # Restrict creation to SystemAdmins only
    if current_user.get("access_level") != "SystemAdmin":
        raise HTTPException(status_code=403, detail="Only System Administrators can create other admins.")
    
    try:
        data = admin.model_dump(exclude_unset=True)
        response = db.add_admin(data)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in create_admin: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create administrator account.")

@router.get("/admins/me", tags=["Admins"])
def get_current_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized.")
    try:
        admin_id = current_user.get("id")
        response = db.get_admin(admin_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_current_admin: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch current admin profile.")

@router.get("/admins/all", tags=["Admins"])
def get_all_admins(current_user: dict = Depends(get_current_user)):
    if current_user.get("access_level") != "SystemAdmin":
        raise HTTPException(status_code=403, detail="Access denied.")
    try:
        response = db.get_all_admins()
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_all_admins: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch administrators.")

@router.put("/admins/update/{admin_id}", tags=["Admins"])
def update_admin(admin_id: str, admin: AdminUpdate, current_user: dict = Depends(get_current_user)):
    if current_user.get("access_level") != "SystemAdmin" and current_user.get("id") != admin_id:
        raise HTTPException(status_code=403, detail="Access denied. You can only update your own profile or must be a System Administrator.")
    try:
        data = admin.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No data provided to update.")
        response = db.edit_admin(admin_id, data)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in update_admin: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update administrator.")

@router.delete("/admins/delete/{admin_id}", tags=["Admins"])
def delete_admin(admin_id: str, current_user: dict = Depends(get_current_user)):
    # 1. Access Control: Only SystemAdmin can perform deletions
    if current_user.get("access_level") != "SystemAdmin":
        raise HTTPException(status_code=403, detail="Security Restriction: Only System Administrators can manage system access credentials.")
    
    try:
        with SessionLocal() as session:
            # 2. Verify target existence and level
            target = session.query(Admins).filter(Admins.id == admin_id).first()
            if not target:
                raise HTTPException(status_code=404, detail="Administrator account not found.")
            
            # 3. RBAC Logic: 
            # - SystemAdmins can delete HR/Manager admins.
            # - SystemAdmins can delete THEMSELVES.
            # - SystemAdmins CANNOT delete OTHER SystemAdmins.
            if target.access_level == "SystemAdmin" and admin_id != current_user.get("id"):
                raise HTTPException(status_code=403, detail="Security Violation: You cannot delete another System Administrator account. Please contact the lead architect.")
            
            # 4. Execute Deletion directly using the current session
            session.delete(target)
            session.commit()
            
            logger.info(f"ADMIN DELETION SUCCESS: Administrator @{target.username} (ID: {admin_id}) removed by @{current_user.get('username')}")
            return {"message": "Administrator account deleted successfully."}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in delete_admin: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete administrator account.")


# ==========================================
#      DEPARTMENTS & ROLES ENDPOINTS
# ==========================================

@router.post("/departments-roles/create", tags=["Departments & Roles"])
def create_department_role(dept_role: DepartmentRoleCreate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied.")
    try:
        data = dept_role.model_dump(exclude_unset=True)
        response = db.add_department_role(data)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in create_department_role: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create department/role classification.")

@router.get("/departments-roles/all", tags=["Departments & Roles"])
def get_all_departments_roles(current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_all_departments_roles()
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_all_departments_roles: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch classifications.")

@router.delete("/departments-roles/delete/{role_id}", tags=["Departments & Roles"])
def delete_department_role(role_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied.")
    try:
        response = db.delete_department_role(role_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in delete_department_role: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete classification.")

@router.post("/employees/request-unlock", tags=["Employees"])
def request_profile_unlock(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "employee":
        raise HTTPException(status_code=403, detail="Only employees can request a profile unlock.")
    try:
        employee_id = current_user.get("id")
        with SessionLocal() as session:
            from src.database.database_tables import Employees
            employee = session.query(Employees).filter(Employees.id == employee_id).first()
            if not employee:
                raise HTTPException(status_code=404, detail="Employee profile not found.")
            employee.profile_edit_requested = True
            session.commit()
            return {"message": "Unlock request submitted successfully."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in request_profile_unlock: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to request profile unlock.")

@router.post("/employees/approve-unlock/{employee_id}", tags=["Employees"])
def approve_profile_unlock(employee_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied. Only administrators can approve unlock requests.")
    try:
        from datetime import datetime, timedelta
        with SessionLocal() as session:
            from src.database.database_tables import Employees
            employee = session.query(Employees).filter(Employees.id == employee_id).first()
            if not employee:
                raise HTTPException(status_code=404, detail="Employee not found.")
            employee.profile_unlocked = True
            employee.profile_unlocked_until = datetime.utcnow() + timedelta(minutes=5)
            employee.profile_edit_requested = False
            session.commit()
            return {"message": f"Profile editing unlocked temporarily for employee {employee.full_name or employee_id}."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in approve_profile_unlock: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to approve profile unlock.")

@router.post("/employees/deny-unlock/{employee_id}", tags=["Employees"])
def deny_profile_unlock(employee_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied. Only administrators can deny unlock requests.")
    try:
        with SessionLocal() as session:
            from src.database.database_tables import Employees
            employee = session.query(Employees).filter(Employees.id == employee_id).first()
            if not employee:
                raise HTTPException(status_code=404, detail="Employee not found.")
            employee.profile_unlocked = False
            employee.profile_unlocked_until = None
            employee.profile_edit_requested = False
            session.commit()
            return {"message": f"Profile unlock request denied for employee {employee.full_name or employee_id}."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in deny_profile_unlock: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to deny profile unlock.")

@router.post("/employees/lock-profile", tags=["Employees"])
def lock_profile(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "employee":
        raise HTTPException(status_code=403, detail="Only employees can lock their profiles.")
    try:
        employee_id = current_user.get("id")
        with SessionLocal() as session:
            from src.database.database_tables import Employees
            employee = session.query(Employees).filter(Employees.id == employee_id).first()
            if not employee:
                raise HTTPException(status_code=404, detail="Employee not found.")
            employee.profile_unlocked = False
            employee.profile_unlocked_until = None
            employee.profile_edit_requested = False
            session.commit()
            return {"message": "Profile locked successfully."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in lock_profile: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to lock profile.")