from fastapi import APIRouter, Depends, HTTPException
import logging
from schemas import (
    EmployeeCreate, EmployeeUpdate, 
    AdminCreate, AdminUpdate, 
    DepartmentRoleCreate, DepartmentRoleUpdate
)
from src.database.database_operations import DatabaseOperations
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
        return handle_response(response)
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
    # Restrict creation to other admins only
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can create other admins.")
    
    try:
        data = admin.model_dump(exclude_unset=True)
        response = db.add_admin(data)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in create_admin: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create administrator account.")

@router.get("/admins/all", tags=["Admins"])
def get_all_admins(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied.")
    try:
        response = db.get_all_admins()
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_all_admins: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch administrators.")

@router.put("/admins/update/{admin_id}", tags=["Admins"])
def update_admin(admin_id: str, admin: AdminUpdate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied.")
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