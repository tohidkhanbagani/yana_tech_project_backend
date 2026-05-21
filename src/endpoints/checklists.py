from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import logging

from src.database.database_create import SessionLocal
from src.database.database_tables import ChecklistTemplate, ProjectChecklistState, Projects
from src.endpoints.auth import get_current_user

router = APIRouter(
    prefix="/checklists",
    tags=["Checklists"]
)

logger = logging.getLogger("Yana_Checklists")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Pydantic Schemas ---
class ChecklistTemplateCreate(BaseModel):
    project_id: str
    phase: str # 'START' or 'END'
    task_description: str

class ChecklistTemplateResponse(BaseModel):
    id: str
    project_id: str
    phase: str
    task_description: str
    
    class Config:
        from_attributes = True

class ChecklistStateUpdateItem(BaseModel):
    checklist_id: str
    is_checked: bool

class ChecklistStateUpdate(BaseModel):
    phase: str
    items: List[ChecklistStateUpdateItem]

class ChecklistStateResponseItem(BaseModel):
    id: str
    checklist_id: str
    task_description: str
    is_checked: bool

class ChecklistStateResponse(BaseModel):
    phase: str
    items: List[ChecklistStateResponseItem]

# --- Admin Settings Endpoints ---

@router.get("/templates/{project_id}", response_model=List[ChecklistTemplateResponse])
def get_checklist_templates(project_id: str, phase: Optional[str] = None, db: Session = Depends(get_db)):
    """Fetch checklist templates for a specific project."""
    query = db.query(ChecklistTemplate).filter(ChecklistTemplate.project_id == project_id)
    if phase:
        query = query.filter(ChecklistTemplate.phase == phase)
    return query.all()

@router.post("/templates", response_model=ChecklistTemplateResponse)
def create_checklist_template(template: ChecklistTemplateCreate, db: Session = Depends(get_db)):
    """Create a new checklist template specific to a project."""
    if template.phase not in ["START", "END"]:
        raise HTTPException(status_code=400, detail="Phase must be 'START' or 'END'")
    
    project = db.query(Projects).filter(Projects.id == template.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    new_template = ChecklistTemplate(
        project_id=template.project_id,
        phase=template.phase,
        task_description=template.task_description
    )
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    return new_template

@router.delete("/templates/{template_id}")
def delete_checklist_template(template_id: str, db: Session = Depends(get_db)):
    """Delete a checklist template."""
    template = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Also delete associated states
    db.query(ProjectChecklistState).filter(ProjectChecklistState.checklist_id == template_id).delete()
    db.delete(template)
    db.commit()
    return {"message": "Template deleted successfully"}

# --- Project Specific Endpoints ---

@router.get("/projects/{project_id}", response_model=ChecklistStateResponse)
def get_project_checklist_state(project_id: str, phase: str, db: Session = Depends(get_db)):
    """
    Fetch the checklist state for a specific project and phase.
    If states don't exist yet for the templates, they are returned as unchecked (dynamically).
    """
    if phase not in ["START", "END"]:
        raise HTTPException(status_code=400, detail="Phase must be 'START' or 'END'")
        
    project = db.query(Projects).filter(Projects.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    templates = db.query(ChecklistTemplate).filter(
        ChecklistTemplate.phase == phase,
        ChecklistTemplate.project_id == project_id
    ).all()
    
    # Fetch existing states
    existing_states = db.query(ProjectChecklistState).filter(
        ProjectChecklistState.project_id == project_id
    ).all()
    state_map = {state.checklist_id: state for state in existing_states}
    
    response_items = []
    for template in templates:
        is_checked = False
        state_id = "new"
        if template.id in state_map:
            is_checked = state_map[template.id].is_checked
            state_id = state_map[template.id].id
            
        response_items.append(ChecklistStateResponseItem(
            id=state_id,
            checklist_id=template.id,
            task_description=template.task_description,
            is_checked=is_checked
        ))
        
    return ChecklistStateResponse(phase=phase, items=response_items)

@router.post("/projects/{project_id}/submit")
def submit_project_checklist_state(project_id: str, payload: ChecklistStateUpdate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Save the state of a checklist when a user submits it from the modal."""
    project = db.query(Projects).filter(Projects.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if payload.phase not in ["START", "END"]:
        raise HTTPException(status_code=400, detail="Phase must be 'START' or 'END'")
        
    # Process each item
    for item in payload.items:
        # Check if template exists and matches phase
        template = db.query(ChecklistTemplate).filter(
            ChecklistTemplate.id == item.checklist_id,
            ChecklistTemplate.phase == payload.phase
        ).first()
        
        if not template:
            continue # Skip invalid templates
            
        # Get or create state
        state = db.query(ProjectChecklistState).filter(
            ProjectChecklistState.project_id == project_id,
            ProjectChecklistState.checklist_id == item.checklist_id
        ).first()
        
        if state:
            state.is_checked = item.is_checked
        else:
            new_state = ProjectChecklistState(
                project_id=project_id,
                checklist_id=item.checklist_id,
                is_checked=item.is_checked
            )
            db.add(new_state)
            
    db.commit()

    # Auto-transition project status on 'START' checklist completion
    if payload.phase == "START" and project.status == "Planning":
        templates = db.query(ChecklistTemplate).filter(
            ChecklistTemplate.project_id == project_id,
            ChecklistTemplate.phase == "START"
        ).all()
        if templates:
            template_ids = [t.id for t in templates]
            checked_count = db.query(ProjectChecklistState).filter(
                ProjectChecklistState.project_id == project_id,
                ProjectChecklistState.checklist_id.in_(template_ids),
                ProjectChecklistState.is_checked == True
            ).count()
            is_completed = (checked_count == len(templates))
        else:
            is_completed = True
            
        if is_completed:
            project.status = "In Progress"
            db.commit()
            logger.info(f"Project {project_id} auto-transitioned to 'In Progress' on 'START' checklist completion.")

    return {"message": "Checklist saved successfully"}
