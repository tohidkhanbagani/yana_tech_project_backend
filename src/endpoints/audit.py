from fastapi import APIRouter, Depends, HTTPException, Query
import logging
from typing import Optional
from src.database.database_operations import DatabaseOperations
from src.endpoints.auth import get_current_user

logger = logging.getLogger("Yana_Audit_Router")
router = APIRouter(prefix="/audit-logs", tags=["Audit & Activity Logs"])
db = DatabaseOperations()

@router.get("", tags=["Audit & Activity Logs"])
def get_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieves system activity and security audit logs.
    Restricted to SystemAdmin and ManagerAdmin users (Admin Panel Exclusive).
    """
    role = current_user.get("role")
    access_level = current_user.get("access_level")
    if role != "admin" and access_level not in ["SystemAdmin", "ManagerAdmin"]:
        raise HTTPException(status_code=403, detail="Unauthorized: Audit logs are reserved for administrative access.")

    try:
        logs_data = db.get_audit_logs(
            page=page,
            limit=limit,
            search=search,
            action=action,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )
        return logs_data
    except Exception as e:
        logger.error(f"Router Error in get_audit_logs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch audit logs.")
