import os
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import engine, Base, get_db, SessionLocal
from models import User, Candidate, Criterion, Score
from scoring import build_ranking, weighted_total
from report import build_pdf
from auth import (hash_password, verify_password, create_token,
                  get_current_user, require_admin)

Base.metadata.create_all(bind=engine)


def ensure_admin():
    """Create the first admin if none exists. Set ADMIN_USERNAME and ADMIN_PASSWORD when deploying."""
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.role == "admin").first():
            db.add(User(name="Admin",
                        username=os.environ.get("ADMIN_USERNAME", "admin"),
                        password_hash=hash_password(os.environ.get("ADMIN_PASSWORD", "admin123")),
                        role="admin"))
            db.commit()
    finally:
        db.close()


ensure_admin()
app = FastAPI(title="Interview Scoreboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------- request shapes ----------
class LoginIn(BaseModel):
    username: str
    password: str

class CandidateIn(BaseModel):
    name: str = Field(min_length=1)
    position: str = "Unspecified role"

class CriterionIn(BaseModel):
    name: str = Field(min_length=1)
    weight: float = Field(ge=0, le=100)

class WeightIn(BaseModel):
    weight: float = Field(ge=0, le=100)

class JudgeIn(BaseModel):
    name: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password: str = Field(min_length=6)

class PasswordIn(BaseModel):
    password: str = Field(min_length=6)

class AccountIn(BaseModel):
    current_password: str
    new_username: Optional[str] = None
    new_password: Optional[str] = Field(default=None, min_length=6)

class ScoreIn(BaseModel):
    candidate_id: int
    marks: Dict[int, int]


# ---------- basics ----------
@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/app/")


@app.post("/seed")
def seed(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Adds demo candidates, criteria, judges and scores. Admin only."""
    if db.query(Candidate).count() > 0:
        return {"message": "Already seeded"}

    crit = [Criterion(name=n, weight=w) for n, w in [
        ("Technical knowledge", 40), ("Problem-solving", 30),
        ("Communication", 20), ("Confidence", 10)]]
    cands = [Candidate(name=n, position="Backend Developer")
             for n in ["Ali Raza", "Sara Khan", "Hina Malik"]]
    judges = [User(name=n, username=u, password_hash=hash_password("judge123"), role="judge")
              for n, u in [("Judge Ahmed", "ahmed"), ("Judge Noor", "noor"), ("Judge Bilal", "bilal")]]
    db.add_all(crit + cands + judges)
    db.flush()

    data = {(0, 0): [8, 6, 7, 9], (1, 0): [7, 7, 8, 8],
            (0, 1): [9, 8, 9, 7], (1, 1): [8, 9, 8, 8], (2, 1): [9, 8, 7, 9],
            (1, 2): [6, 7, 6, 5]}
    for (j, c), marks in data.items():
        for k, m in zip(crit, marks):
            db.add(Score(judge_id=judges[j].id, candidate_id=cands[c].id,
                         criterion_id=k.id, marks=m))
    db.commit()
    return {"message": "Demo data added. Demo judges use the password judge123"}


# ---------- login and account ----------
@app.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username.strip()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong username or password")
    return {"token": create_token(user.id), "role": user.role,
            "name": user.name, "username": user.username}


@app.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "name": user.name, "username": user.username, "role": user.role}


@app.post("/account")
def update_account(body: AccountIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    changed = False
    new_name = (body.new_username or "").strip()
    if new_name and new_name != user.username:
        if db.query(User).filter(User.username == new_name, User.id != user.id).first():
            raise HTTPException(status_code=400, detail="Username already taken")
        user.username = new_name
        changed = True
    if body.new_password:
        user.password_hash = hash_password(body.new_password)
        changed = True
    if not changed:
        raise HTTPException(status_code=400, detail="Nothing to change")
    db.commit()
    return {"message": "Account updated", "username": user.username}


# ---------- candidates ----------
@app.get("/candidates")
def list_candidates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [{"id": c.id, "name": c.name, "position": c.position}
            for c in db.query(Candidate).all()]

@app.post("/candidates")
def add_candidate(body: CandidateIn, db: Session = Depends(get_db),
                  admin: User = Depends(require_admin)):
    c = Candidate(name=body.name.strip(), position=body.position.strip() or "Unspecified role")
    db.add(c); db.commit()
    return {"id": c.id, "name": c.name, "position": c.position}

@app.delete("/candidates/{cid}")
def delete_candidate(cid: int, db: Session = Depends(get_db),
                     admin: User = Depends(require_admin)):
    c = db.get(Candidate, cid)
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    db.query(Score).filter(Score.candidate_id == cid).delete()
    db.delete(c); db.commit()
    return {"deleted": cid}


# ---------- criteria ----------
@app.get("/criteria")
def list_criteria(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [{"id": k.id, "name": k.name, "weight": k.weight}
            for k in db.query(Criterion).all()]

@app.post("/criteria")
def add_criterion(body: CriterionIn, db: Session = Depends(get_db),
                  admin: User = Depends(require_admin)):
    k = Criterion(name=body.name.strip(), weight=body.weight)
    db.add(k); db.commit()
    return {"id": k.id, "name": k.name, "weight": k.weight}

@app.put("/criteria/{kid}")
def change_weight(kid: int, body: WeightIn, db: Session = Depends(get_db),
                  admin: User = Depends(require_admin)):
    k = db.get(Criterion, kid)
    if not k:
        raise HTTPException(status_code=404, detail="Criterion not found")
    k.weight = body.weight
    db.commit()
    return {"id": k.id, "name": k.name, "weight": k.weight}

@app.delete("/criteria/{kid}")
def delete_criterion(kid: int, db: Session = Depends(get_db),
                     admin: User = Depends(require_admin)):
    k = db.get(Criterion, kid)
    if not k:
        raise HTTPException(status_code=404, detail="Criterion not found")
    db.query(Score).filter(Score.criterion_id == kid).delete()
    db.delete(k); db.commit()
    return {"deleted": kid}


# ---------- judges ----------
@app.get("/judges")
def list_judges(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return [{"id": u.id, "name": u.name, "username": u.username}
            for u in db.query(User).filter(User.role == "judge").all()]

@app.post("/judges")
def add_judge(body: JudgeIn, db: Session = Depends(get_db),
              admin: User = Depends(require_admin)):
    if db.query(User).filter(User.username == body.username.strip()).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    u = User(name=body.name.strip(), username=body.username.strip(),
             password_hash=hash_password(body.password), role="judge")
    db.add(u); db.commit()
    return {"id": u.id, "name": u.name, "username": u.username}

@app.put("/judges/{jid}/password")
def reset_judge_password(jid: int, body: PasswordIn, db: Session = Depends(get_db),
                         admin: User = Depends(require_admin)):
    u = db.get(User, jid)
    if not u or u.role != "judge":
        raise HTTPException(status_code=404, detail="Judge not found")
    u.password_hash = hash_password(body.password)
    db.commit()
    return {"message": "Password updated"}

@app.delete("/judges/{jid}")
def delete_judge(jid: int, db: Session = Depends(get_db),
                 admin: User = Depends(require_admin)):
    u = db.get(User, jid)
    if not u or u.role != "judge":
        raise HTTPException(status_code=404, detail="Judge not found")
    db.query(Score).filter(Score.judge_id == jid).delete()
    db.delete(u); db.commit()
    return {"deleted": jid}


# ---------- ranking and export ----------
@app.get("/ranking")
def ranking(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return build_ranking(db.query(Candidate).all(),
                         db.query(Criterion).all(),
                         db.query(Score).all())

@app.get("/export/pdf")
def export_pdf(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    criteria = db.query(Criterion).all()
    ranking_rows = build_ranking(db.query(Candidate).all(), criteria, db.query(Score).all())
    judge_count = db.query(User).filter(User.role == "judge").count()
    pdf = build_pdf(ranking_rows, criteria, judge_count)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="interview-results.pdf"'})


# ---------- judge scoring ----------
@app.post("/scores")
def submit_scores(body: ScoreIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    if user.role != "judge":
        raise HTTPException(status_code=403, detail="Judges only")
    if not db.get(Candidate, body.candidate_id):
        raise HTTPException(status_code=404, detail="Candidate not found")

    criteria = db.query(Criterion).all()
    if set(body.marks.keys()) != {k.id for k in criteria}:
        raise HTTPException(status_code=400, detail="Give a mark for every criterion")
    if any(m < 0 or m > 10 for m in body.marks.values()):
        raise HTTPException(status_code=400, detail="Marks must be between 0 and 10")

    already = db.query(Score).filter(Score.judge_id == user.id,
                                     Score.candidate_id == body.candidate_id).first()
    if already:
        raise HTTPException(status_code=409, detail="You already scored this candidate")

    for criterion_id, marks in body.marks.items():
        db.add(Score(judge_id=user.id, candidate_id=body.candidate_id,
                     criterion_id=criterion_id, marks=marks))
    db.commit()

    weights = {k.id: k.weight for k in criteria}
    return {"message": "Scores submitted",
            "weighted_total": round(weighted_total(body.marks, weights), 2)}


@app.get("/my-scores")
def my_scores(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    weights = {k.id: k.weight for k in db.query(Criterion).all()}
    by_candidate = {}
    for s in db.query(Score).filter(Score.judge_id == user.id).all():
        by_candidate.setdefault(s.candidate_id, {})[s.criterion_id] = s.marks
    return [{"candidate_id": cid, "marks": m,
             "weighted_total": round(weighted_total(m, weights), 2)}
            for cid, m in by_candidate.items()]


# ---------- the web page (keep this at the very bottom) ----------
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/app", StaticFiles(directory=FRONTEND, html=True), name="app")