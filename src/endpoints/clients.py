from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.database.database_tables import Clients
from src.database.database_operations import DatabaseOperations
from src.database.database_create import SessionLocal
import schemas

router = APIRouter()

# Dependency to get the DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/clients/create", tags=["Clients"])
def create_client(client: schemas.ClientCreate, db: Session = Depends(get_db)):
    """Creates a new client in the system."""
    db_ops = DatabaseOperations()
    
    # Check if a client with the same name already exists
    existing_client = db.query(Clients).filter(Clients.name == client.name).first()
    if existing_client:
        raise HTTPException(status_code=400, detail="A client with this name already exists.")

    new_client = Clients(
        name=client.name,
        company=client.company,
        email=client.email,
        phone=client.phone,
        address=client.address
    )
    
    try:
        db.add(new_client)
        db.commit()
        db.refresh(new_client)
        return db_ops.model_to_dict(new_client)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create client: {str(e)}")

@router.get("/clients/all", tags=["Clients"])
def get_all_clients(db: Session = Depends(get_db)):
    """Retrieves a list of all clients."""
    db_ops = DatabaseOperations()
    try:
        clients = db.query(Clients).all()
        return [db_ops.model_to_dict(c) for c in clients]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch clients: {str(e)}")

@router.put("/clients/update/{client_id}", tags=["Clients"])
def update_client(client_id: str, client_update: schemas.ClientUpdate, db: Session = Depends(get_db)):
    """Updates an existing client's details."""
    db_ops = DatabaseOperations()
    existing_client = db.query(Clients).filter(Clients.id == client_id).first()
    if not existing_client:
        raise HTTPException(status_code=404, detail="Client not found.")
    
    # Check name uniqueness if name is being changed
    if client_update.name is not None and client_update.name != existing_client.name:
        name_check = db.query(Clients).filter(Clients.name == client_update.name).first()
        if name_check:
            raise HTTPException(status_code=400, detail="Another client with this name already exists.")

    update_data = client_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(existing_client, key, value)
    
    try:
        db.commit()
        db.refresh(existing_client)
        return db_ops.model_to_dict(existing_client)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update client: {str(e)}")

@router.delete("/clients/delete/{client_id}", tags=["Clients"])
def delete_client(client_id: str, db: Session = Depends(get_db)):
    """Deletes a client from the system."""
    existing_client = db.query(Clients).filter(Clients.id == client_id).first()
    if not existing_client:
        raise HTTPException(status_code=404, detail="Client not found.")
    
    try:
        db.delete(existing_client)
        db.commit()
        return {"detail": "Client deleted successfully."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete client: {str(e)}")