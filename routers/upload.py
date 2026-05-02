import os
import uuid
import shutil
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import fitz  # PyMuPDF

from database import get_db
from routers.auth import get_current_user
import crud.user as crud
import models
import schemas.user as schemas

router = APIRouter(prefix="/auth", tags=["Uploads"])

UPLOAD_DIR = "uploads"
PROFILE_IMG_DIR = os.path.join(UPLOAD_DIR, "profiles")
os.makedirs(PROFILE_IMG_DIR, exist_ok=True)

@router.post("/upload-profile-image")
def upload_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(PROFILE_IMG_DIR, unique_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # URL to access the image (assuming FastAPI is running with /uploads mounted)
    file_url = f"/uploads/profiles/{unique_filename}"
    
    # Update user profile
    current_user.profile_image = file_url
    db.commit()
    db.refresh(current_user)
    
    return {"url": file_url}

@router.post("/upload-base-cv")
def upload_base_cv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Read the PDF and extract text
    try:
        pdf_content = file.file.read()
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        
        current_user.base_cv = text.strip()
        db.commit()
        db.refresh(current_user)
        
        return {"message": "Base CV extracted and saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract text from PDF: {str(e)}")

@router.delete("/base-cv")
def remove_base_cv(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    current_user.base_cv = None
    db.commit()
    db.refresh(current_user)
    return {"message": "Base CV removed successfully"}
