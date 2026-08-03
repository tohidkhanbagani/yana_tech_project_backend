from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Optional
import os
import shutil
import uuid
from src.database.database_operations import DatabaseOperations

router = APIRouter(prefix="/obligations", tags=["Operational Obligations"])

UPLOAD_DIR = os.path.join(os.getcwd(), "data", "obligation_proofs")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.get("/all")
def get_all_obligations():
    """Retrieves all active operational obligations."""
    db_ops = DatabaseOperations()
    try:
        return db_ops.get_all_operational_obligations(active_only=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch obligations: {str(e)}")

@router.get("/pending-alerts")
def get_pending_alerts(role: Optional[str] = None):
    """Retrieves active pending/overdue obligations requiring persistent admin/manager popups."""
    db_ops = DatabaseOperations()
    try:
        return db_ops.get_pending_operational_obligations(role=role)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch pending alerts: {str(e)}")

@router.post("")
def create_obligation(
    title: str = Form(...),
    category: str = Form("Office Rent"),
    amount: float = Form(0.0),
    due_day: int = Form(5),
    recurrence: str = Form("Monthly"),
    assigned_role: str = Form("All")
):
    """Create a new recurring operational obligation (Rent, Bills, Taxes)."""
    db_ops = DatabaseOperations()
    try:
        return db_ops.create_operational_obligation(
            title=title,
            category=category,
            amount=amount,
            due_day=due_day,
            recurrence=recurrence,
            assigned_role=assigned_role
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create obligation: {str(e)}")

@router.post("/{obligation_id}/complete")
async def complete_obligation(
    obligation_id: str,
    remarks: str = Form(...),
    completed_by_user_id: str = Form("Admin"),
    completed_by_role: str = Form("Admin"),
    amount_paid: Optional[float] = Form(None),
    custom_next_due: Optional[str] = Form(None),
    proof_image: Optional[UploadFile] = File(None)
):
    """Mark an operational obligation as completed with remarks and proof image upload."""
    db_ops = DatabaseOperations()
    proof_url = "N/A"
    
    if proof_image and proof_image.filename:
        try:
            ext = os.path.splitext(proof_image.filename)[1]
            filename = f"proof_{uuid.uuid4().hex}{ext}"
            file_path = os.path.join(UPLOAD_DIR, filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(proof_image.file, buffer)
            proof_url = f"/data/obligation_proofs/{filename}"
        except Exception as e:
            print(f"Warning: Proof image save failed: {str(e)}")

    try:
        return db_ops.complete_operational_obligation(
            obligation_id=obligation_id,
            user_id=completed_by_user_id,
            role=completed_by_role,
            remarks=remarks,
            amount_paid=amount_paid,
            custom_next_due=custom_next_due,
            proof_image_url=proof_url
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to complete obligation: {str(e)}")

@router.delete("/{obligation_id}")
def delete_obligation(obligation_id: str):
    """Deactivate / remove an operational obligation."""
    db_ops = DatabaseOperations()
    success = db_ops.delete_operational_obligation(obligation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Obligation not found or already deleted.")
    return {"detail": "Operational obligation removed successfully."}
