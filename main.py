from fastapi import FastAPI, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import bcrypt # Naya import (passlib hata diya)
import jwt
import razorpay
from datetime import datetime, timedelta
from pydantic import BaseModel
from models import User
import models
import schemas
from database import engine, SessionLocal
import os
import httpx
from pydantic import BaseModel



# --- SECURITY SETTINGS ---
# CryptContext hata diya, ab direct bcrypt use karenge
SECRET_KEY = "war-project-super-secret-key" 
ALGORITHM = "HS256"
security = HTTPBearer()

# Create Database Tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="WAR Project API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://war-frontend-psi.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Token Generator
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=24)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Token Verifier
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired! Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# --- ROUTES ---

@app.get("/")
def read_root():
    return {"status": "success", "message": "WAR Project server is running!"}

# SIGNUP ROUTE
@app.post("/signup") 
def signup(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(
        (models.User.email == user_data.email) | 
        (models.User.username == user_data.username)
    ).first()
    
    if existing_user:
        if existing_user.email == user_data.email:
            raise HTTPException(status_code=400, detail="Email already registered!")
        if existing_user.username == user_data.username:
            raise HTTPException(status_code=400, detail="User ID already taken! Choose another one.")

    # FIX: Direct bcrypt hashing
    hashed_pwd = bcrypt.hashpw(user_data.password[:72].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    new_user = models.User(
        name=user_data.name,
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_pwd
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "Warrior registered successfully!", "user_id": new_user.username}

# /token ROUTE
@app.post("/token")
def login_for_access_token(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == username).first()
    
    # FIX: Direct bcrypt verification
    if not db_user or not bcrypt.checkpw(password[:72].encode('utf-8'), db_user.hashed_password.encode('utf-8')):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": db_user.email})
    return {"access_token": access_token, "token_type": "bearer", "message": "Login successful!"}

# LOGIN ROUTE
@app.post("/login")
def login(user_data: dict, db: Session = Depends(get_db)):
    email = user_data.get("email")
    password = user_data.get("password")
    
    db_user = db.query(models.User).filter(models.User.email == email).first()
    
    # FIX: Direct bcrypt verification
    if not db_user or not bcrypt.checkpw(password[:72].encode('utf-8'), db_user.hashed_password.encode('utf-8')):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": db_user.email})
    return {"access_token": access_token, "token_type": "bearer", "message": "Login successful!"}

# --- (Baki code same rahega, maine niche copy kar diya hai) ---

# Secure Study Tracking Route
@app.post("/study-session")
def save_study_session(session_data: schemas.StudyRecord, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_session = models.StudySession(user_id=current_user.id, duration_minutes=session_data.duration_minutes, date=session_data.date)
    db.add(new_session)
    db.commit()
    progress = db.query(models.UserProgress).filter(models.UserProgress.user_id == current_user.id).first()
    if not progress:
        progress = models.UserProgress(user_id=current_user.id, xp=0, streak_count=0, last_active_date=None)
        db.add(progress)
        db.commit()
        db.refresh(progress)
    progress.xp += session_data.duration_minutes
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    yesterday_str = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    if progress.last_active_date == yesterday_str:
        progress.streak_count += 1
    elif progress.last_active_date != today_str:
        progress.streak_count = 1
    progress.last_active_date = today_str
    db.commit()
    return {"message": f"Awesome job! {session_data.duration_minutes} minutes saved.", "user_email": current_user.email}

@app.get("/analytics")
def get_user_analytics(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_sessions = db.query(models.StudySession).filter(models.StudySession.user_id == current_user.id).all()
    total_minutes = sum(session.duration_minutes for session in user_sessions)
    total_sessions = len(user_sessions)
    total_quizzes = db.query(models.QuizSubmission).filter(models.QuizSubmission.user_id == current_user.id).count()
    correct_quizzes = db.query(models.QuizSubmission).filter(models.QuizSubmission.user_id == current_user.id, models.QuizSubmission.is_correct == 1).count()
    accuracy = round((correct_quizzes / total_quizzes) * 100) if total_quizzes > 0 else 0
    progress = db.query(models.UserProgress).filter(models.UserProgress.user_id == current_user.id).first()
    return {"email": current_user.email, "name": current_user.name, "total_study_minutes": total_minutes, "xp": progress.xp if progress else 0, "accuracy_percent": accuracy}

@app.get("/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    all_users = db.query(models.User).all()
    leaderboard_data = []
    for user in all_users:
        user_sessions = db.query(models.StudySession).filter(models.StudySession.user_id == user.id).all()
        total_time = sum(session.duration_minutes for session in user_sessions)
        if total_time > 0:
            leaderboard_data.append({"name": user.name, "username": user.username, "total_minutes": total_time})
    leaderboard_data.sort(key=lambda x: x["total_minutes"], reverse=True)
    for index, player in enumerate(leaderboard_data):
        player["rank"] = index + 1
    return {"leaderboard": leaderboard_data}

@app.post("/notes")
def create_note(note: schemas.NoteCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_note = models.Note(user_id=current_user.id, title=note.title, content=note.content)
    db.add(new_note)
    db.commit()
    return {"message": "Note saved successfully!"}

@app.get("/notes")
def get_my_notes(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_notes = db.query(models.Note).filter(models.Note.user_id == current_user.id).all()
    return {"notes": user_notes}

def get_admin_user(current_user: models.User = Depends(get_current_user)):
    if current_user.email != "ravik61285@gmail.com":
        raise HTTPException(status_code=403, detail="Access Denied")
    return current_user

@app.get("/admin/dashboard")
def admin_dashboard(admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    return {"message": "Welcome, Boss."}

@app.delete("/admin/users/{user_id}")
def delete_user(user_id: int, admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    user_to_delete = db.query(models.User).filter(models.User.id == user_id).first()
    db.delete(user_to_delete)
    db.commit()
    return {"message": "User banished."}

@app.post("/premium/checkout")
def create_subscription_order(current_user: models.User = Depends(get_current_user)):
    return {"message": "Payment system in sandbox."}

@app.post("/admin/groups")
def create_exam_group(group_data: schemas.GroupCreate, admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    new_group = models.ExamGroup(name=group_data.name, description=group_data.description)
    db.add(new_group)
    db.commit()
    return {"message": "Group created."}

@app.get("/groups")
def get_all_groups(db: Session = Depends(get_db)):
    groups = db.query(models.ExamGroup).all()
    return {"groups": groups}

@app.post("/groups/{group_id}/join")
def join_group(group_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_member = models.GroupMembership(group_id=group_id, user_id=current_user.id, role="member")
    db.add(new_member)
    db.commit()
    return {"message": "Successfully joined."}

@app.post("/admin/groups/{group_id}/posts")
def create_group_post(group_id: int, post_data: schemas.PostCreate, admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    new_post = models.GroupPost(group_id=group_id, author_id=admin.id, content=post_data.content, file_url=post_data.file_url, created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    db.add(new_post)
    db.commit()
    return {"message": "Material deployed."}

@app.get("/groups/{group_id}/posts")
def get_group_posts(group_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    posts = db.query(models.GroupPost).filter(models.GroupPost.group_id == group_id).all()
    return {"posts": posts}

@app.post("/admin/groups/{group_id}/quizzes")
def create_group_quiz(group_id: int, quiz_data: schemas.GroupQuizCreate, admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    new_quiz = models.GroupQuiz(group_id=group_id, question=quiz_data.question, option_a=quiz_data.option_a, option_b=quiz_data.option_b, option_c=quiz_data.option_c, option_d=quiz_data.option_d, correct_option=quiz_data.correct_option.upper())
    db.add(new_quiz)
    db.commit()
    return {"message": "Quiz deployed."}

@app.get("/groups/{group_id}/quizzes")
def get_group_quizzes(group_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    quizzes = db.query(models.GroupQuiz).filter(models.GroupQuiz.group_id == group_id).all()
    return {"quizzes": quizzes}

@app.post("/quizzes/{quiz_id}/submit")
def submit_quiz_answer(quiz_id: int, submission_data: schemas.QuizSubmit, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    quiz = db.query(models.GroupQuiz).filter(models.GroupQuiz.id == quiz_id).first()
    is_correct = 1 if submission_data.selected_option.upper() == quiz.correct_option.upper() else 0
    new_submission = models.QuizSubmission(quiz_id=quiz_id, user_id=current_user.id, selected_option=submission_data.selected_option.upper(), is_correct=is_correct, submitted_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    db.add(new_submission)
    db.commit()
    return {"status": "success", "is_correct": is_correct == 1}

@app.post("/feedback")
def submit_user_feedback(feedback_data: dict, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_feedback = models.UserFeedback(user_id=current_user.id, category=feedback_data.get("category", "suggestion"), message=feedback_data.get("message"), created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    db.add(new_feedback)
    db.commit()
    return {"status": "success"}

@app.get("/admin/feedbacks")
def get_all_feedbacks(admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    feedbacks = db.query(models.UserFeedback).all()
    return {"feedbacks": feedbacks}

# main.py ke end mein ye add kar do
@app.get("/users/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {"email": current_user.email}

    

    # --- AI CHAT LOGIC ---
class ChatRequest(BaseModel):
    message: str

@app.post("/api/kimi-chat")
async def chat_with_model(request: ChatRequest):
    # Render ke Environment Variables se key uthayege
    api_key = os.getenv("NVIDIA_API_KEY")
    model_name = os.getenv("MODEL_NAME", "moonshotai/kimi-k2.6") 
    
    invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": request.message}],
        "max_tokens": 1024,
        "temperature": 0.7,
        "stream": False
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(invoke_url, headers=headers, json=payload, timeout=60.0)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        
        # --- AI CHAT LOGIC ---
class ChatRequest(BaseModel):
    message: str

@app.post("/api/kimi-chat")
async def chat_with_model(request: ChatRequest):
    # Render Dashboard mein NVIDIA_API_KEY set karo, yahan hardcode mat karna!
    api_key = os.getenv("NVIDIA_API_KEY") 
    model_name = os.getenv("MODEL_NAME", "moonshotai/kimi-k2.6")
    
    invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": request.message}],
        "max_tokens": 1024,
        "temperature": 0.7,
        "stream": False
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(invoke_url, headers=headers, json=payload, timeout=60.0)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))