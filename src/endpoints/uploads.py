
import os
import json
import aiofiles
import mimetypes
from src.endpoints.auth import handle_response, get_current_user
from pathlib import Path, PurePath
from schemas import ProjectCreate, ProjectUpdate
from src.database.database_create import SessionLocal
from src.database.database_tables import Projects as DBProject
from src.database.database_operations import DatabaseOperations
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
import re
import requests
from io import BytesIO
import PyPDF2



router = APIRouter(
    prefix="/uploads",
    tags=["Uploads"]
)


db = DatabaseOperations()



@router.post("/image/", tags=["Uploads"])
async def upload_image(
    file: UploadFile = File(..., description="Upload the image/document"),
    current_user: dict = Depends(get_current_user),
    image_type: str = "adhar",
    sub_type: str = "front",
    employee_id: str = None
    ):

    # Configuration for new storage architecture
    storage_config = {
        "images": ["adhar", "pancard", "profile", "qr_code"],
        "documents": ["resume"],
        "sub_folders": ["front", "back"]
    }
    
    # 1. Determine Target Employee
    target_id = current_user['id']
    if employee_id and employee_id != current_user['id']:
        if current_user.get("access_level") != "SystemAdmin" and current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only Administrators can upload for other employees.")
        target_id = employee_id

    # Compliance Lock Check
    if current_user.get("role") == "employee" and image_type in ["adhar", "pancard", "qr_code"]:
        from src.database.database_tables import Employees
        with SessionLocal() as session:
            emp = session.query(Employees).filter(Employees.id == target_id).first()
            if emp and emp.compliance_verified:
                raise HTTPException(status_code=403, detail="Access Denied: Compliance uploads are verified and locked by HR/Admin.")

    # 2. Validation
    valid_types = storage_config["images"] + storage_config["documents"]
    if image_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid type. Must be one of: {', '.join(valid_types)}")

    # 2.1 File extension and MIME type validation
    filename_ext = os.path.splitext(file.filename)[1].lower()
    allowed_exts = [".jpg", ".jpeg", ".png", ".pdf"]
    allowed_mimes = ["image/jpeg", "image/jpg", "image/png", "application/pdf"]
    if filename_ext not in allowed_exts or file.content_type not in allowed_mimes:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed formats: JPG, JPEG, PNG, PDF.")

    # 2.2 File Size Check (Max 5MB)
    file.file.seek(0, 2)
    file_size = file.file.tell()
    await file.seek(0)
    if file_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds the 5MB limit.")

    # 2.3 Image Corruption and Resolution Check
    if filename_ext in [".jpg", ".jpeg", ".png"]:
        try:
            from PIL import Image
            from io import BytesIO
            file_bytes = await file.read()
            img = Image.open(BytesIO(file_bytes))
            img.verify()
            
            # Reopen to check dimensions
            img = Image.open(BytesIO(file_bytes))
            width, height = img.size
            if width < 150 or height < 150:
                raise HTTPException(status_code=400, detail="Image resolution must be at least 150x150 pixels.")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid or corrupted image file.")
        finally:
            await file.seek(0)
    elif filename_ext == ".pdf":
        try:
            from io import BytesIO
            file_bytes = await file.read()
            reader = PyPDF2.PdfReader(BytesIO(file_bytes))
            _ = len(reader.pages)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid or corrupted PDF file.")
        finally:
            await file.seek(0)

    # 3. Setup Directory Structure
    # Pattern: data/uploads/[images|documents]/[type]/[sub_type if exists]/[employee_id].[ext]
    base_category = "images" if image_type in storage_config["images"] else "documents"
    base_directory = f"data/uploads/{base_category}/{image_type}/"
    
    if sub_type in storage_config["sub_folders"]:
        base_directory += f"{sub_type}/"
    
    os.makedirs(base_directory, exist_ok=True)
    
    ext = filename_ext[1:] if filename_ext else "dat"
    
    # Filename is unique to the employee in that specific type folder
    safe_name = f"{target_id}.{ext}"
    file_path = os.path.join(base_directory, safe_name).replace("\\", "/")

    try:
        # 4. Write File
        async with aiofiles.open(file_path, "wb") as out_file:
            while content := await file.read(1024 * 1024):
                await out_file.write(content)
        
        # 5. Dynamic mapping to DB column
        column_mapping = {
            "profile": "photo",
            "qr_code": "qr_code",
            "resume": "resume",
            "pancard_front": "pan_front",
            "pancard_back": "pan_back",
            "adhar_front": "adhar_front",
            "adhar_back": "adhar_back"
        }
        
        lookup_key = f"{image_type}_{sub_type}" if sub_type in storage_config["sub_folders"] else image_type
        column_name = column_mapping.get(lookup_key, image_type)

        db.edit_employee(
            employee_id=target_id,
            data={column_name: file_path}
        )

        return {
            "message": "Upload successful",
            "file_path": file_path,
            "employee_id": target_id,
            "column": column_name
        }
    except Exception as e:
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.delete("/image/", tags=["Uploads"])
async def delete_image(
    image_type: str,
    sub_type: str = "front",
    employee_id: str = None,
    current_user: dict = Depends(get_current_user)
):
    # 1. Determine Target Employee
    target_id = current_user['id']
    if employee_id and employee_id != current_user['id']:
        if current_user.get("access_level") != "SystemAdmin" and current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only Administrators can manage other employee files.")
        target_id = employee_id

    # Compliance Lock Check
    if current_user.get("role") == "employee" and image_type in ["adhar", "pancard", "qr_code"]:
        from src.database.database_tables import Employees
        with SessionLocal() as session:
            emp = session.query(Employees).filter(Employees.id == target_id).first()
            if emp and emp.compliance_verified:
                raise HTTPException(status_code=403, detail="Access Denied: Compliance uploads are verified and locked by HR/Admin.")

    # 2. Configuration & Validation
    storage_config = {
        "images": ["adhar", "pancard", "profile", "qr_code"],
        "documents": ["resume"],
        "sub_folders": ["front", "back"]
    }
    valid_types = storage_config["images"] + storage_config["documents"]
    if image_type not in valid_types:
        raise HTTPException(status_code=400, detail="Invalid file type.")

    # 3. Dynamic mapping to DB column
    column_mapping = {
        "profile": "photo",
        "qr_code": "qr_code",
        "resume": "resume",
        "pancard_front": "pan_front",
        "pancard_back": "pan_back",
        "adhar_front": "adhar_front",
        "adhar_back": "adhar_back"
    }
    
    lookup_key = f"{image_type}_{sub_type}" if sub_type in storage_config["sub_folders"] else image_type
    column_name = column_mapping.get(lookup_key, image_type)

    # 4. Fetch Employee & Clean up
    with SessionLocal() as session:
        from src.database.database_tables import Employees
        employee = session.query(Employees).filter(Employees.id == target_id).first()
        if not employee:
            raise HTTPException(status_code=404, detail="Employee record not found.")
        
        file_path = getattr(employee, column_name, None)
        
        # 5. Physical Deletion
        if file_path and file_path != "N/A":
            try:
                full_path = Path(file_path)
                if full_path.exists():
                    os.remove(full_path)
            except Exception as e:
                print(f"File Deletion Error (Non-Fatal): {str(e)}")
        
        # 6. Database Update
        setattr(employee, column_name, "N/A")
        session.commit()

    return {"message": "File deleted successfully", "column": column_name}

# --- PDF Parsing Algorithm ---
def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Advanced SRS Parser: Uses heuristics to detect sections, merge paragraphs,
    and filter out noise like page numbers/headers without using expensive models.
    """
    try:
        reader = PyPDF2.PdfReader(BytesIO(file_bytes))
        structured_data = []
        current_section = {"heading": "Document Overview", "content": []}
        
        # Buffer for paragraph merging
        para_buffer = []
        
        def flush_para():
            if para_buffer:
                clean_text = " ".join(para_buffer).strip()
                if clean_text:
                    current_section["content"].append(clean_text)
                para_buffer.clear()

        for page in reader.pages:
            text = page.extract_text()
            if not text:
                continue
                
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    flush_para()
                    continue
                
                # 1. Noise Filter (Page numbers, common footers)
                if re.match(r'^(Page|PAGE)\s*\d+|^\d+$|^[0-9\/\-]{8,}$', line, re.I):
                    continue
                
                # 2. Heading Detection Heuristics
                is_heading = False
                if len(line) < 120:
                    # Numbered Section: 1.0, 2.1, 3.1.2
                    if re.match(r'^(\d+\.)+\d*\s+[A-Z]', line) or re.match(r'^\d+\s+[A-Z][a-z]+', line):
                        is_heading = True
                    # Common SRS Major Sections
                    elif re.match(r'^(Introduction|Purpose|Scope|Overall Description|System Features|Functional Requirements|External Interface|Non-functional Requirements|Glossary|Appendix)', line, re.I):
                        is_heading = True
                    # Short All-Caps (Title case)
                    elif line.isupper() and len(line.split()) < 10:
                        is_heading = True

                # 3. Structural Processing
                if is_heading:
                    flush_para()
                    # Only append previous section if it has data
                    if current_section["content"] or current_section["heading"] != "Document Overview":
                        structured_data.append(current_section)
                    current_section = {"heading": line, "content": []}
                else:
                    # Detect list items/bullets - break para if new list item
                    is_list_item = re.match(r'^[\s]*[\u2022\-\*\u25CF]\s*|^[\s]*[a-z0-9]\)\s*', line)
                    if is_list_item:
                        flush_para()
                        para_buffer.append(line)
                        flush_para() # Keep lists separate
                    else:
                        # Paragraph merging: if previous line didn't end with a full stop, merge it
                        if para_buffer and not para_buffer[-1].endswith(('.', '!', '?', ':', ';')):
                            para_buffer.append(line)
                        else:
                            flush_para()
                            para_buffer.append(line)
            
            flush_para() # End of page

        # Final flush
        if current_section["content"] or current_section["heading"] != "Document Overview":
            structured_data.append(current_section)
            
        if not structured_data:
            return json.dumps([{"heading": "Status", "content": ["The document seems to be image-based or non-structured. Detailed parsing could not be completed automatically."]}])
            
        return json.dumps(structured_data, indent=2)
    except Exception as e:
        return json.dumps([{"heading": "Parsing Error", "content": [f"System encountered an issue while decoding the PDF: {str(e)}"]}])

def sanitize_filename(name: str) -> str:
    """Removes spaces and illegal characters for clean OS storage."""
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', name)

@router.post("/srs/", tags=["Uploads"])
async def upload_srs_document(
    project_id: str = Form(...),
    project_name: str = Form(...),
    document_title: str = Form(...),
    version: str = Form("v1.0"),
    file: UploadFile = File(None),
    cloud_link: str = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Dedicated SRS Endpoint.
    1. Validates strictly for PDF.
    2. Downloads external links if provided instead of file.
    3. Creates specific directory pattern.
    4. Parses the PDF into searchable text.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only Admins can manage SRS documents.")

    if not file and not cloud_link:
        raise HTTPException(status_code=400, detail="Must provide either a PDF file or a direct Cloud Link.")

    file_content = None
    file_path_to_save = None

    # Determine safe names
    safe_proj = sanitize_filename(project_name)
    safe_title = sanitize_filename(document_title)
    safe_version = sanitize_filename(version)
    
    # Format: project_id+project_name+version+document_title.pdf
    target_filename = f"{project_id}_{safe_proj}_{safe_version}_{safe_title}.pdf"
    target_folder = "data/uploads/documents/srs/"
    os.makedirs(target_folder, exist_ok=True)
    target_path = os.path.join(target_folder, target_filename)

    # --- SCENARIO A: FILE UPLOAD ---
    if file:
        if not file.filename.lower().endswith('.pdf') or file.content_type != 'application/pdf':
            raise HTTPException(status_code=400, detail=f"Invalid format ({file.content_type}). SRS documents must strictly be PDFs.")
        
        file_content = await file.read()
        
        # Save physically
        async with aiofiles.open(target_path, "wb") as out_file:
            await out_file.write(file_content)
        file_path_to_save = target_path

    # --- SCENARIO B: CLOUD LINK PROVIDED ---
    elif cloud_link:
        try:
            # Attempt to automatically fetch the PDF from the provided link
            headers = {"User-Agent": "YanaOS-Agent"}
            response = requests.get(cloud_link, headers=headers, timeout=10)
            
            # Verify if the fetched link is actually a PDF
            if response.status_code == 200 and 'application/pdf' in response.headers.get('Content-Type', ''):
                file_content = response.content
                async with aiofiles.open(target_path, "wb") as out_file:
                    await out_file.write(file_content)
                file_path_to_save = target_path
            else:
                # If it's a generic webpage (like a Google Doc viewer), we just save the link 
                # and skip deep parsing, as we cannot extract raw bytes easily.
                file_path_to_save = cloud_link
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch cloud document: {str(e)}")

    # --- PARSING ALGORITHM ---
    parsed_text = "Document linked successfully. (External web viewer - parsing bypassed)."
    if file_content:
        parsed_text = extract_text_from_pdf(file_content)

    # --- SAVE TO DATABASE ---
    # We map this directly using database operations. 
    # (Ensure db.add_srs_document accepts 'parsed_content')
    srs_payload = {
        "project_id": project_id,
        "document_title": document_title,
        "version": version,
        "file_url_or_path": file_path_to_save,
        "parsed_content": parsed_text,
        "status": "Approved",
        "approved_by": current_user.get("username")
    }
    
    try:
        saved_record = db.add_srs_document(srs_payload)
        return handle_response(saved_record)
    except HTTPException as e:
        if file_path_to_save and not file_path_to_save.startswith('http') and os.path.exists(file_path_to_save):
            os.remove(file_path_to_save)
        raise e
    except Exception as e:
        if file_path_to_save and not file_path_to_save.startswith('http') and os.path.exists(file_path_to_save):
            os.remove(file_path_to_save)
        raise HTTPException(status_code=500, detail=f"Failed to process SRS: {str(e)}")



