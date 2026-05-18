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
        response = db.edit_employee(employee_id, data)
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