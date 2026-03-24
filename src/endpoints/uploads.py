
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
    file: UploadFile = File(..., description="Upload the image"),
    current_user: dict = Depends(get_current_user),
    image_type:str="adhar",
    sub_type:str="front"
    ):

    type_dict = {
        "types":["adhar","pan","profile", "qr"],
        "adhar":{
            "types":["front","back"],
            "folder":"adhar"
        },
        "pan":{
            "types":["front","back"],
            "folder":"pan"
        },
        "profile":{
            "types":["profile"],
            "folder":"profile"
        },
        "qr":{
            "types":["code"],
            "folder":"qr"
        }
    }
    # 1. Early Validation (Type)
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only images allowed.")

    # 2. Early Validation (Size hint - doesn't read file yet)
    MAX_SIZE = 5 * 1024 * 1024  # 5MB
    if file.size > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File size too large maximum 5MB allowed")

    if image_type not in type_dict["types"]:
        raise HTTPException(status_code=400, detail="invalid image type")
    
    if sub_type not in type_dict[image_type]["types"]:
        raise HTTPException(status_code=400, detail="invalid sub type")
    

    # 3. Setup Directory
    base_directory = f"data/uploads/employees/{current_user['id']}/{type_dict[image_type]['folder']}/"
    os.makedirs(base_directory, exist_ok=True)
    
    # Sanitize filename to prevent path traversal
    safe_name = f"{current_user['id']}_{type_dict[image_type]['folder']}_{sub_type}.{mimetypes.guess_extension(file.content_type)[1:]}"
    file_path = os.path.join(base_directory, safe_name)

    try:
        # 4. Stream Write (Efficient & Fast)
        async with aiofiles.open(file_path, "wb") as out_file:
            while content := await file.read(1024 * 1024):  # Read in 1MB chunks
                await out_file.write(content)
                
                # Dynamic mapping of the column name based on database DBProject mapping logic
                if image_type == "profile":
                    column_name = "photo"
                elif image_type == "qr":
                    column_name = "qr_code"
                else:
                    column_name = f"{type_dict[image_type]['folder']}_{sub_type}"

                updated_data = db.edit_employee(
                    employee_id=current_user['id'],
                    data={column_name:file_path}
                    )
        return {
            "message": "File uploaded successfully",
            "file_path": file_path,
            "file_details": {
                "file_name": file.filename,
                "file_type": file.content_type,
                "file_size": file.size
            },
            "employee updated data":updated_data
        }
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# --- PDF Parsing Algorithm ---
def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Robust algorithm to parse text from raw PDF bytes into a structured JSON string."""
    import json
    import re
    try:
        reader = PyPDF2.PdfReader(BytesIO(file_bytes))
        structured_data = []
        current_section = {"heading": "Document Overview", "content": []}
        
        for page in reader.pages:
            text = page.extract_text()
            if text:
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    is_heading = False
                    # Heuristics for headings: Length < 100, no terminal punctuation
                    if len(line) < 100 and not line.endswith(('.', ':', ',', ';', '?')):
                        # Uppercase or Title Case
                        if line.isupper() or line.istitle():
                            is_heading = True
                        # Numbered heading e.g., "1. Introduction" or "1.1. Scope"
                        elif re.match(r'^(\d+\.)+\s*[A-Za-z]', line):
                            is_heading = True
                        elif re.match(r'^\d+\s+[A-Z]', line):
                            is_heading = True
                            
                    if is_heading:
                        if current_section["content"] or current_section["heading"] != "Document Overview":
                            structured_data.append(current_section)
                        current_section = {"heading": line, "content": []}
                    else:
                        current_section["content"].append(line)
        
        if current_section["content"] or current_section["heading"] != "Document Overview":
            structured_data.append(current_section)
            
        if not structured_data:
            return json.dumps([{"heading": "Status", "content": ["No parseable text found in this PDF (might be image-based)."]}])
            
        return json.dumps(structured_data)
    except Exception as e:
        import json
        return json.dumps([{"heading": "Parsing Error", "content": [f"Could not extract text from document: {str(e)}"]}])

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
    target_folder = f"data/uploads/projects/{project_id}_{safe_proj}/"
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