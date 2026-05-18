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
            reason=req.reason
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



