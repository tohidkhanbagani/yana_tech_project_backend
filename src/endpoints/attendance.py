from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
import logging
from typing import Optional
from src.database.database_operations import DatabaseOperations
from src.endpoints.auth import get_current_user, handle_response

logger = logging.getLogger("Yana_Attendance_Endpoint")

router = APIRouter()
db = DatabaseOperations()

class CheckInRequest(BaseModel):
    ip_address: Optional[str] = None

class LeaveRequestSubmit(BaseModel):
    start_date: str
    end_date: str
    reason: str
    leave_type: Optional[str] = "Paid Leave"
    half_day_option: Optional[str] = "Full Day"
    total_days: Optional[float] = 1.0
    pending_work_summary: Optional[str] = "N/A"
    backup_employee_id: Optional[str] = "N/A"
    deployment_pending: Optional[str] = "No"

class LeaveRequestStatusUpdate(BaseModel):
    status: str

@router.post("/attendance/check-in", tags=["Attendance"])
def employee_check_in(req: CheckInRequest, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        # Prevent admins from checking in if this is only for employees
        # But we'll allow anyone for now, or assume current_user.id is employee_id
        ip_addr = req.ip_address or request.client.host
        response = db.check_in(current_user["id"], ip_address=ip_addr)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in check_in: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to check in.")

@router.post("/attendance/check-out", tags=["Attendance"])
def employee_check_out(current_user: dict = Depends(get_current_user)):
    try:
        response = db.check_out(current_user["id"])
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in check_out: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to check out.")

@router.get("/attendance/all", tags=["Attendance"])
def get_all_attendance(current_user: dict = Depends(get_current_user)):
    try:
        # Check admin role? For now rely on frontend or basic role check
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Access denied.")
        response = db.get_all_attendance()
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_all_attendance: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch attendance records.")

@router.get("/attendance/me", tags=["Attendance"])
def get_my_attendance(current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_employee_attendance(current_user["id"])
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_my_attendance: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch your attendance records.")

@router.get("/attendance/login-history", tags=["Attendance"])
def get_all_login_history(current_user: dict = Depends(get_current_user)):
    try:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Access denied.")
        response = db.get_all_login_history()
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_all_login_history: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch login history.")

@router.get("/attendance/leave-requests", tags=["Attendance"])
def get_all_leave_requests(current_user: dict = Depends(get_current_user)):
    try:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Access denied.")
        response = db.get_all_leave_requests()
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_all_leave_requests: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch leave requests.")

@router.post("/attendance/leave-requests", tags=["Attendance"])
def submit_leave_request(req: LeaveRequestSubmit, current_user: dict = Depends(get_current_user)):
    try:
        response = db.create_leave_request(
            employee_id=current_user["id"],
            start_date=req.start_date,
            end_date=req.end_date,
            reason=req.reason,
            leave_type=req.leave_type,
            half_day_option=req.half_day_option,
            total_days=req.total_days,
            pending_work_summary=req.pending_work_summary,
            backup_employee_id=req.backup_employee_id,
            deployment_pending=req.deployment_pending
        )
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in submit_leave_request: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit leave request.")

@router.get("/attendance/leave-requests/me", tags=["Attendance"])
def get_my_leave_requests(current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_employee_leave_requests(current_user["id"])
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in get_my_leave_requests: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch your leave requests.")

@router.get("/attendance/leave-requests/backup-coverages", tags=["Attendance"])
def get_backup_coverages(current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_backup_coverages_by_employee(current_user["id"])
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_backup_coverages: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve backup coverages.")

@router.put("/attendance/leave-requests/{leave_id}/status", tags=["Attendance"])
def update_leave_request_status(leave_id: str, req: LeaveRequestStatusUpdate, current_user: dict = Depends(get_current_user)):
    try:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Access denied.")
        response = db.update_leave_request_status(leave_id, req.status)
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in update_leave_request_status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update leave request status.")

@router.post("/attendance/leave-requests/{leave_id}/cancel", tags=["Attendance"])
def cancel_leave_request(leave_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.cancel_leave_request_by_employee(leave_id, current_user["id"])
        import json
        resp_dict = json.loads(response)
        if "error" in resp_dict:
            raise HTTPException(status_code=400, detail=resp_dict["error"])
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in cancel_leave_request: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to cancel leave request.")

@router.get("/attendance/notifications", tags=["Attendance"])
def get_notifications(current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_user_notifications(current_user["id"])
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_notifications: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch notifications.")

@router.post("/attendance/notifications/{notif_id}/read", tags=["Attendance"])
def mark_notification_read(notif_id: str, current_user: dict = Depends(get_current_user)):
    try:
        response = db.mark_notification_as_read(notif_id, current_user["id"])
        import json
        resp_dict = json.loads(response)
        if "error" in resp_dict:
            raise HTTPException(status_code=400, detail=resp_dict["error"])
        return handle_response(response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Router Error in mark_notification_read: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to mark notification as read.")

class HolidaySubmit(BaseModel):
    name: str
    date: str  # YYYY-MM-DD
    holiday_type: str  # 'Public' or 'Company'

class WorkingHoursUpdate(BaseModel):
    working_hours: float
    employee_ids: Optional[list] = None
    department: Optional[str] = None
    role_id: Optional[str] = None

@router.get("/attendance/holidays", tags=["Attendance"])
def get_holidays(current_user: dict = Depends(get_current_user)):
    try:
        response = db.get_company_holidays()
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in get_holidays: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch holidays.")

@router.post("/attendance/holidays", tags=["Attendance"])
def create_holiday(req: HolidaySubmit, current_user: dict = Depends(get_current_user)):
    try:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Access denied.")
        response = db.create_company_holiday(req.name, req.date, req.holiday_type)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in create_holiday: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create holiday.")

@router.delete("/attendance/holidays/{holiday_id}", tags=["Attendance"])
def delete_holiday(holiday_id: str, current_user: dict = Depends(get_current_user)):
    try:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Access denied.")
        response = db.delete_company_holiday(holiday_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in delete_holiday: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete holiday.")

@router.post("/attendance/working-hours", tags=["Attendance"])
def update_working_hours(req: WorkingHoursUpdate, current_user: dict = Depends(get_current_user)):
    try:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Access denied.")
        response = db.bulk_update_working_hours(req.working_hours, req.employee_ids, req.department, req.role_id)
        return handle_response(response)
    except Exception as e:
        logger.error(f"Router Error in update_working_hours: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update working hours.")




