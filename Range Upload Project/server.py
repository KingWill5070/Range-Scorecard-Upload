# ============================================================
# SECTION 1 — IMPORTS, APP SETUP, DB INIT, STARTUP ADMIN SEED
# ============================================================

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid
import os

from database import SessionLocal, Base, engine
from models import User, RangeCard
from auth_utils import hash_password, verify_password, create_access_token, decode_access_token

# -------------------------
# Initialize DB
# -------------------------
Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# OAuth2 Security Scheme
# -------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# -------------------------
# Dependency: DB Session
# -------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -------------------------
# Startup: Ensure Admin Exists
# -------------------------
@app.on_event("startup")
def ensure_admin_exists():
    db = SessionLocal()
    admin = db.query(User).filter(User.role == "admin").first()
    if not admin:
        new_admin = User(
            user_id=str(uuid.uuid4()),
            username="admin",
            hashed_password=hash_password("Admin123!"),
            role="admin",
            supervisor_id=None
        )
        db.add(new_admin)
        db.commit()
    db.close()
# ============================================================
# SECTION 2 — AUTH HELPERS + LEGACY TERM HELPERS
# ============================================================

def get_legacy_term(score: int) -> str:
    if score >= 36:
        return "Expert"
    elif score >= 30:
        return "Sharpshooter"
    elif score >= 23:
        return "Marksman"
    return "Unqualified"

def extract_score_from_description(description: str) -> int | None:
    digits = "".join(ch for ch in description if ch.isdigit())
    if digits:
        try:
            return int(digits)
        except ValueError:
            return None
    return None

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.user_id == payload["user_id"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user

def require_role(user: User, allowed_roles: list):
    if user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
# ============================================================
# SECTION 3 — LOGIN + UNIVERSAL REGISTRATION
# ============================================================

# -------------------------
# LOGIN — FIXED FOR SWAGGER + FRONTEND
# -------------------------
@app.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    username = form_data.username
    password = form_data.password

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"user_id": user.user_id, "role": user.role})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "user_id": user.user_id
    }

# -------------------------
# UNIVERSAL REGISTRATION
# -------------------------
class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str              # soldier, nco, officer, admin
    supervisor_id: str | None = None

@app.post("/register")
def register_user(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    hashed = hash_password(payload.password)

    new_user = User(
        user_id=str(uuid.uuid4()),
        username=payload.username,
        hashed_password=hashed,
        role=payload.role,
        supervisor_id=payload.supervisor_id
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "User registered", "user_id": new_user.user_id}
# ============================================================
# SECTION 4 — ADMIN ROUTES
# ============================================================

@app.post("/admin/create-user")
def admin_create_user(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(current_user, ["admin"])

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = User(
        user_id=str(uuid.uuid4()),
        username=username,
        hashed_password=hash_password(password),
        role=role,
        supervisor_id=None
    )

    db.add(new_user)
    db.commit()

    return {"message": "User created successfully"}

@app.get("/admin/metrics")
def admin_metrics(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["admin"])

    return {
        "total_users": db.query(User).count(),
        "total_soldiers": db.query(User).filter(User.role == "soldier").count(),
        "total_ncos": db.query(User).filter(User.role == "nco").count(),
        "total_officers": db.query(User).filter(User.role == "officer").count(),
        "total_uploads": db.query(RangeCard).count()
    }

@app.get("/admin/users")
def admin_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["admin"])
    users = db.query(User).all()
    return [{"user_id": u.user_id, "username": u.username, "role": u.role} for u in users]

@app.post("/admin/update-role")
def admin_update_role(
    user_id: str = Form(...),
    new_role: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(current_user, ["admin"])

    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = new_role
    db.commit()

    return {"message": "Role updated successfully"}

@app.delete("/admin/delete-user")
def admin_delete_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(current_user, ["admin"])

    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # delete soldier uploads if applicable
    db.query(RangeCard).filter(RangeCard.soldier_id == user.user_id).delete()

    db.delete(user)
    db.commit()

    return {"message": "User deleted"}

@app.get("/admin/hierarchy")
def admin_hierarchy(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["admin"])

    officers = db.query(User).filter(User.role == "officer").all()
    ncos = db.query(User).filter(User.role == "nco").all()
    soldiers = db.query(User).filter(User.role == "soldier").all()

    result = []
    for officer in officers:
        officer_ncos = [n for n in ncos if n.supervisor_id == officer.user_id]
        officer_block = {
            "user_id": officer.user_id,
            "username": officer.username,
            "ncos": []
        }
        for nco in officer_ncos:
            nco_soldiers = [s for s in soldiers if s.supervisor_id == nco.user_id]
            officer_block["ncos"].append({
                "user_id": nco.user_id,
                "username": nco.username,
                "soldiers": [
                    {"user_id": s.user_id, "username": s.username}
                    for s in nco_soldiers
                ]
            })
        result.append(officer_block)

    return {"officers": result}


# ============================================================
# SECTION 5 — SOLDIER ROUTES
# ============================================================

@app.post("/soldier/uploads")
def soldier_upload(
    file: UploadFile = File(...),
    description: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(current_user, ["soldier"])

    if current_user.supervisor_id is None:
        raise HTTPException(status_code=400, detail="Soldier has no assigned NCO")

    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)

    file_id = str(uuid.uuid4())
    saved_filename = f"{file_id}_{file.filename}"
    file_path = os.path.join(upload_dir, saved_filename)

    with open(file_path, "wb") as f:
        f.write(file.file.read())

    new_record = RangeCard(
        file_id=file_id,
        soldier_id=current_user.user_id,
        filename=saved_filename,
        description=description,
        status="pending",
        uploaded_at="",
        legacy_term="Unqualified"
    )

    db.add(new_record)
    db.commit()

    return {"message": "Upload successful", "file_id": file_id}

@app.get("/soldier/uploads")
def soldier_view_uploads(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["soldier"])
    uploads = db.query(RangeCard).filter(RangeCard.soldier_id == current_user.user_id).all()
    return [
        {
            "file_id": u.file_id,
            "filename": u.filename,
            "description": u.description,
            "status": u.status,
            "uploaded_at": u.uploaded_at,
            "legacy_term": u.legacy_term
        }
        for u in uploads
    ]
# ============================================================
# SECTION 6 — NCO ROUTES
# ============================================================

@app.post("/nco/assign-soldier")
def assign_soldier(
    soldier_id: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(current_user, ["nco"])

    soldier = db.query(User).filter(User.user_id == soldier_id).first()
    if not soldier or soldier.role != "soldier":
        raise HTTPException(status_code=404, detail="Soldier not found")

    soldier.supervisor_id = current_user.user_id
    db.commit()

    return {"message": "Soldier assigned successfully"}

@app.get("/nco/readiness")
def nco_readiness(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["nco"])

    soldiers = db.query(User).filter(User.supervisor_id == current_user.user_id).all()
    soldier_ids = [s.user_id for s in soldiers]

    uploads = db.query(RangeCard).filter(RangeCard.soldier_id.in_(soldier_ids)).all()

    total_uploads = len(uploads)
    approved = len([u for u in uploads if u.status == "approved"])
    rejected = len([u for u in uploads if u.status == "rejected"])
    pending = len([u for u in uploads if u.status == "pending"])

    readiness = round((approved / total_uploads) * 100, 2) if total_uploads > 0 else 0

    return {
        "total_soldiers": len(soldiers),
        "total_uploads": total_uploads,
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "readiness_percentage": readiness
    }

@app.get("/nco/soldiers")
def nco_soldiers(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["nco"])

    soldiers = db.query(User).filter(User.supervisor_id == current_user.user_id).all()
    soldier_ids = [s.user_id for s in soldiers]

    uploads = db.query(RangeCard).filter(RangeCard.soldier_id.in_(soldier_ids)).all()

    result = []
    for soldier in soldiers:
        soldier_uploads = [u for u in uploads if u.soldier_id == soldier.user_id]
        total = len(soldier_uploads)
        approved = len([u for u in soldier_uploads if u.status == "approved"])
        pending = len([u for u in soldier_uploads if u.status == "pending"])

        readiness = round((approved / total) * 100, 2) if total > 0 else 0

        result.append({
            "user_id": soldier.user_id,
            "username": soldier.username,
            "completed_uploads": approved,
            "pending_items": pending,
            "readiness_percentage": readiness
        })

    return result
@app.get("/nco/unassigned-soldiers")
def nco_unassigned_soldiers(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["nco"])
    soldiers = db.query(User).filter(User.role == "soldier", User.supervisor_id.is_(None)).all()
    return [{"user_id": s.user_id, "username": s.username} for s in soldiers]
@app.get("/nco/uploads")
def nco_uploads(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["nco"])
    soldiers = db.query(User).filter(User.supervisor_id == current_user.user_id).all()
    soldier_ids = [s.user_id for s in soldiers]
    uploads = db.query(RangeCard).filter(RangeCard.soldier_id.in_(soldier_ids)).all()
    return [
        {
            "file_id": u.file_id,
            "filename": u.filename,
            "description": u.description,
            "status": u.status,
            "legacy_term": u.legacy_term
        }
        for u in uploads
    ]

@app.post("/nco/update-status")
def nco_update_status(
    file_id: str = Form(...),
    status: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(current_user, ["nco"])

    upload = db.query(RangeCard).filter(RangeCard.file_id == file_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    # only allow NCO to touch uploads from their soldiers
    soldier = db.query(User).filter(User.user_id == upload.soldier_id).first()
    if not soldier or soldier.supervisor_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not your soldier")

    upload.status = status

    score = extract_score_from_description(upload.description)
    if score is not None and status == "approved":
        upload.legacy_term = get_legacy_term(score)

    db.commit()
    return {"message": "Status updated"}
@app.get("/nco/uploads")
def nco_uploads(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["nco"])

    soldiers = db.query(User).filter(User.supervisor_id == current_user.user_id).all()
    soldier_ids = [s.user_id for s in soldiers]

    uploads = db.query(RangeCard).filter(RangeCard.soldier_id.in_(soldier_ids)).all()

    return [
        {
            "file_id": u.file_id,
            "filename": u.filename,
            "description": u.description,
            "status": u.status,
            "legacy_term": u.legacy_term
        }
        for u in uploads
    ]



# ============================================================
# SECTION 7 — OFFICER ROUTES
# ============================================================

@app.post("/officer/assign-nco")
def officer_assign_nco(
    nco_id: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(current_user, ["officer"])

    nco = db.query(User).filter(User.user_id == nco_id).first()
    if not nco or nco.role != "nco":
        raise HTTPException(status_code=404, detail="NCO not found")

    nco.supervisor_id = current_user.user_id
    db.commit()

    return {"message": "NCO assigned to officer"}

@app.get("/officer/readiness")
def officer_readiness(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["officer"])

    ncos = db.query(User).filter(User.supervisor_id == current_user.user_id).all()
    nco_ids = [n.user_id for n in ncos]

    soldiers = db.query(User).filter(User.supervisor_id.in_(nco_ids)).all()
    soldier_ids = [s.user_id for s in soldiers]

    uploads = db.query(RangeCard).filter(RangeCard.soldier_id.in_(soldier_ids)).all()

    total_uploads = len(uploads)
    approved = len([u for u in uploads if u.status == "approved"])
    rejected = len([u for u in uploads if u.status == "rejected"])
    pending = len([u for u in uploads if u.status == "pending"])

    readiness = round((approved / total_uploads) * 100, 2) if total_uploads > 0 else 0

    return {
        "total_soldiers": len(soldiers),
        "total_uploads": total_uploads,
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "readiness_percentage": readiness
    }
@app.get("/officer/uploads")
def get_officer_uploads(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["officer"])

    ncos = db.query(User).filter(User.supervisor_id == current_user.user_id).all()
    nco_ids = [n.user_id for n in ncos]

    soldiers = db.query(User).filter(User.supervisor_id.in_(nco_ids)).all()
    soldier_ids = [s.user_id for s in soldiers]

    uploads = db.query(RangeCard).filter(RangeCard.soldier_id.in_(soldier_ids)).all()

    return [
        {
            "file_id": u.file_id,
            "filename": u.filename,
            "description": u.description,
            "status": u.status,
            "legacy_term": u.legacy_term,
            "url": f"/files/{u.filename}"   # ⭐ ADD THIS
        }
        for u in uploads
    ]


@app.post("/officer/update-status")
def officer_update_status(
    file_id: str = Form(...),
    status: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(current_user, ["officer"])

    upload = db.query(RangeCard).filter(RangeCard.file_id == file_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    # only allow officer to touch uploads in their platoon
    soldier = db.query(User).filter(User.user_id == upload.soldier_id).first()
    if not soldier:
        raise HTTPException(status_code=404, detail="Soldier not found")

    nco = db.query(User).filter(User.user_id == soldier.supervisor_id).first()
    if not nco or nco.supervisor_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not in your platoon")

    upload.status = status

    score = extract_score_from_description(upload.description)
    if score is not None and status == "approved":
        upload.legacy_term = get_legacy_term(score)

    db.commit()
    return {"message": "Status updated"}
@app.get("/officer/unassigned-ncos")
def officer_unassigned_ncos(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["officer"])
    ncos = db.query(User).filter(User.role == "nco", User.supervisor_id.is_(None)).all()
    return [{"user_id": n.user_id, "username": n.username} for n in ncos]
@app.get("/officer/ncos")
def get_officer_ncos(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["officer"])

    ncos = db.query(User).filter(User.supervisor_id == current_user.user_id).all()

    return [
        {
            "user_id": n.user_id,
            "username": n.username
        }
        for n in ncos
    ]
@app.get("/officer/soldiers")
def get_officer_soldiers(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["officer"])

    # Get NCOs assigned to this officer
    ncos = db.query(User).filter(User.supervisor_id == current_user.user_id).all()
    nco_ids = [n.user_id for n in ncos]

    # Get soldiers assigned to those NCOs
    soldiers = db.query(User).filter(User.supervisor_id.in_(nco_ids)).all()

    return [
        {
            "user_id": s.user_id,
            "username": s.username
        }
        for s in soldiers
    ]
@app.get("/officer/uploads")
def get_officer_uploads(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(current_user, ["officer"])

    # Get NCOs assigned to officer
    ncos = db.query(User).filter(User.supervisor_id == current_user.user_id).all()
    nco_ids = [n.user_id for n in ncos]

    # Get soldiers assigned to those NCOs
    soldiers = db.query(User).filter(User.supervisor_id.in_(nco_ids)).all()
    soldier_ids = [s.user_id for s in soldiers]

    # Get uploads from those soldiers
    uploads = db.query(FileUpload).filter(FileUpload.user_id.in_(soldier_ids)).all()

    return [
        {
            "file_id": u.file_id,
            "filename": u.filename,
            "description": u.description,
            "status": u.status,
            "legacy_term": u.legacy_term
        }
        for u in uploads
    ]





# ============================================================
# SECTION 8 — STATIC FILE MOUNTS
# ============================================================

app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/files", StaticFiles(directory="uploads"), name="files")
