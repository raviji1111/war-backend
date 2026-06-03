from fastapi import FastAPI, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import jwt
import razorpay
from datetime import datetime, timedelta
from pydantic import BaseModel

import models
import schemas
from database import engine, SessionLocal

# --- SECURITY SETTINGS ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "war-project-super-secret-key" 
ALGORITHM = "HS256"
security = HTTPBearer()

# Create Database Tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="WAR Project API")

# Trust Next.js frontend
# Trust Next.js frontend
app.add_middleware(
    CORSMiddleware,
    # Yahan maine localhost ke saath tumhari live site ka URL bhi add kar diya hai
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

# Token Verifier (The Bouncer)
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

# # SIGNUP ROUTE
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

    # FIX: Yahan hum password ko 72 characters tak limit/truncate kar rahe hain
    # Taaki bcrypt error na de.
    hashed_pwd = pwd_context.hash(user_data.password[:72])

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
    
    # FIX: password[:72] use karo taaki verify function crash na ho
    if not db_user or not pwd_context.verify(password[:72], db_user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": db_user.email})
    return {"access_token": access_token, "token_type": "bearer", "message": "Login successful!"}

# LOGIN ROUTE
@app.post("/login")
def login(user_data: dict, db: Session = Depends(get_db)):
    email = user_data.get("email")
    password = user_data.get("password")
    
    db_user = db.query(models.User).filter(models.User.email == email).first()
    
    # FIX: password[:72] use karo
    if not db_user or not pwd_context.verify(password[:72], db_user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": db_user.email})
    return {"access_token": access_token, "token_type": "bearer", "message": "Login successful!"}


# Secure Study Tracking Route
@app.post("/study-session")
def save_study_session(
    session_data: schemas.StudyRecord, 
    current_user: models.User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    new_session = models.StudySession(
        user_id=current_user.id,
        duration_minutes=session_data.duration_minutes,
        date=session_data.date
    )
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

    if progress.last_active_date == today_str:
        pass  
    elif progress.last_active_date == yesterday_str:
        progress.streak_count += 1  
        progress.last_active_date = today_str
    else:
        progress.streak_count = 1   
        progress.last_active_date = today_str

    db.commit()
    
    return {
        "message": f"Awesome job! {session_data.duration_minutes} minutes saved. Progress updated!", 
        "user_email": current_user.email
    }


# Analytics Route
@app.get("/analytics")
def get_user_analytics(
    current_user: models.User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    user_sessions = db.query(models.StudySession).filter(models.StudySession.user_id == current_user.id).all()
    total_minutes = sum(session.duration_minutes for session in user_sessions)
    total_sessions = len(user_sessions)
    
    total_quizzes = db.query(models.QuizSubmission).filter(models.QuizSubmission.user_id == current_user.id).count()
    correct_quizzes = db.query(models.QuizSubmission).filter(models.QuizSubmission.user_id == current_user.id, models.QuizSubmission.is_correct == 1).count()
    wrong_quizzes = total_quizzes - correct_quizzes
    accuracy = round((correct_quizzes / total_quizzes) * 100) if total_quizzes > 0 else 0
    
    progress = db.query(models.UserProgress).filter(models.UserProgress.user_id == current_user.id).first()
    if not progress:
        progress = models.UserProgress(user_id=current_user.id, xp=0, streak_count=0, last_active_date=None)
        db.add(progress)
        db.commit()
        db.refresh(progress)

    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    yesterday_str = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    if progress.last_active_date and progress.last_active_date != today_str and progress.last_active_date != yesterday_str:
        progress.streak_count = 0
        db.commit()
    
    return {
        "email": current_user.email,
        "name": current_user.name,
        "username": current_user.username,
        "total_study_minutes": total_minutes,
        "total_sessions": total_sessions,
        "xp": progress.xp,                        
        "streak": progress.streak_count,          
        "quiz_stats": {
            "total_attempted": total_quizzes,
            "correct": correct_quizzes,
            "wrong": wrong_quizzes,
            "accuracy_percent": accuracy
        },
        "message": f"Warrior {current_user.name} has studied for {total_minutes} mins and cleared {correct_quizzes} missions!"
    }

# Social Leaderboard Route
@app.get("/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    all_users = db.query(models.User).all()
    leaderboard_data = []
    
    for user in all_users:
        user_sessions = db.query(models.StudySession).filter(models.StudySession.user_id == user.id).all()
        total_time = sum(session.duration_minutes for session in user_sessions)
        
        if total_time > 0:
            leaderboard_data.append({
                "name": user.name or "Unknown Warrior",
                "username": user.username or "warrior",
                "total_minutes": total_time
            })
    
    leaderboard_data.sort(key=lambda x: x["total_minutes"], reverse=True)
    
    for index, player in enumerate(leaderboard_data):
        player["rank"] = index + 1
        
    return {"leaderboard": leaderboard_data}


# Content System (Notes)
@app.post("/notes")
def create_note(
    note: schemas.NoteCreate, 
    current_user: models.User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    new_note = models.Note(
        user_id=current_user.id, 
        title=note.title, 
        content=note.content
    )
    db.add(new_note)
    db.commit()
    
    return {"message": f"Note '{note.title}' saved successfully!"}

@app.get("/notes")
def get_my_notes(
    current_user: models.User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    user_notes = db.query(models.Note).filter(models.Note.user_id == current_user.id).all()
    return {"total_notes": len(user_notes), "notes": user_notes}


# Admin System 👑
def get_admin_user(current_user: models.User = Depends(get_current_user)):
    if current_user.email != "ravik61285@gmail.com":
        raise HTTPException(status_code=403, detail="Access Denied: Admins Only 👑")
    return current_user


@app.get("/admin/dashboard")
def admin_dashboard(
    admin: models.User = Depends(get_admin_user), 
    db: Session = Depends(get_db)
):
    total_users = db.query(models.User).count()
    total_sessions = db.query(models.StudySession).count()
    total_notes = db.query(models.Note).count()
    
    return {
        "message": f"Welcome to the WAR Room, Boss.",
        "admin_email": admin.email,
        "metrics": {
            "total_users": total_users,
            "total_study_sessions": total_sessions,
            "total_notes_saved": total_notes
        }
    }


@app.delete("/admin/users/{user_id}")
def delete_user(
    user_id: int, 
    admin: models.User = Depends(get_admin_user), 
    db: Session = Depends(get_db)
):
    user_to_delete = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user_to_delete.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete yourself!")

    db.delete(user_to_delete)
    db.commit()
    
    return {"message": f"User {user_to_delete.email} has been permanently banished."}


# Payment System 💳
RAZORPAY_KEY_ID = "rzp_test_YourKeyIdHere"
RAZORPAY_KEY_SECRET = "YourKeySecretHere"
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

@app.post("/premium/checkout")
def create_subscription_order(
    current_user: models.User = Depends(get_current_user)
):
    try:
        order_amount = 9900
        order_currency = "INR"
        razorpay_order = razorpay_client.order.create(dict(
            amount=order_amount,
            currency=order_currency,
            receipt=f"receipt_user_{current_user.id}",
            payment_capture=1 
        ))
        return {
            "message": "Checkout session created!",
            "order_id": razorpay_order["id"],
            "currency": order_currency,
            "amount": 99 
        }
    except Exception as e:
        return {"error": "Payment system is currently in sandbox mode."}
    

# Community & Exam Groups 📚
@app.post("/admin/groups")
def create_exam_group(
    group_data: schemas.GroupCreate,
    admin: models.User = Depends(get_admin_user), 
    db: Session = Depends(get_db)
):
    new_group = models.ExamGroup(name=group_data.name, description=group_data.description)
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    
    admin_member = models.GroupMembership(group_id=new_group.id, user_id=admin.id, role="admin")
    db.add(admin_member)
    db.commit()
    
    return {"message": f"Group '{new_group.name}' created! WAR Room is ready.", "group_id": new_group.id}


@app.get("/groups")
def get_all_groups(db: Session = Depends(get_db)):
    groups = db.query(models.ExamGroup).all()
    return {"groups": groups}


@app.post("/groups/{group_id}/join")
def join_group(
    group_id: int,
    current_user: models.User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    existing = db.query(models.GroupMembership).filter(
        models.GroupMembership.group_id == group_id,
        models.GroupMembership.user_id == current_user.id
    ).first()
    
    if existing:
        return {"message": "You are already a warrior in this group."}
        
    new_member = models.GroupMembership(group_id=group_id, user_id=current_user.id, role="member")
    db.add(new_member)
    db.commit()
    return {"message": "Successfully joined the group!"}


@app.post("/admin/groups/{group_id}/posts")
def create_group_post(
    group_id: int,
    post_data: schemas.PostCreate,
    admin: models.User = Depends(get_admin_user), 
    db: Session = Depends(get_db)
):
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    new_post = models.GroupPost(
        group_id=group_id,
        author_id=admin.id,
        content=post_data.content,
        file_url=post_data.file_url,
        created_at=now_str
    )
    db.add(new_post)
    db.commit()
    return {"message": "Material deployed to the group successfully!"}


@app.get("/groups/{group_id}/posts")
def get_group_posts(
    group_id: int,
    current_user: models.User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    posts = db.query(models.GroupPost).filter(models.GroupPost.group_id == group_id).all()
    return {"total_posts": len(posts), "posts": posts}


# LIVE MCQ QUIZ SYSTEM 🎯
@app.post("/admin/groups/{group_id}/quizzes")
def create_group_quiz(
    group_id: int,
    quiz_data: schemas.GroupQuizCreate, 
    admin: models.User = Depends(get_admin_user), 
    db: Session = Depends(get_db)
):
    if quiz_data.correct_option.upper() not in ["A", "B", "C", "D"]:
        raise HTTPException(status_code=400, detail="Correct option must be A, B, C, or D")

    new_quiz = models.GroupQuiz(
        group_id=group_id,
        question=quiz_data.question,
        option_a=quiz_data.option_a,
        option_b=quiz_data.option_b,
        option_c=quiz_data.option_c,
        option_d=quiz_data.option_d,
        correct_option=quiz_data.correct_option.upper()
    )
    db.add(new_quiz)
    db.commit()
    db.refresh(new_quiz)
    return {"message": "🔥 Quiz deployed successfully to the battalion!", "quiz_id": new_quiz.id}


@app.get("/groups/{group_id}/quizzes")
def get_group_quizzes(
    group_id: int,
    current_user: models.User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    quizzes = db.query(models.GroupQuiz).filter(models.GroupQuiz.group_id == group_id).all()
    quizzes_with_status = []
    for quiz in quizzes:
        submission = db.query(models.QuizSubmission).filter(
            models.QuizSubmission.quiz_id == quiz.id,
            models.QuizSubmission.user_id == current_user.id
        ).first()
        
        quizzes_with_status.append({
            "id": quiz.id,
            "group_id": quiz.group_id,
            "question": quiz.question,
            "option_a": quiz.option_a,
            "option_b": quiz.option_b,
            "option_c": quiz.option_c,
            "option_d": quiz.option_d,
            "correct_option": quiz.correct_option,
            "user_answer": submission.selected_option if submission else None 
        })
    return {"total_quizzes": len(quizzes), "quizzes": quizzes_with_status}


# QUIZ ANALYTICS ROUTES 📊
@app.post("/quizzes/{quiz_id}/submit")
def submit_quiz_answer(
    quiz_id: int,
    submission_data: schemas.QuizSubmit,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    already_submitted = db.query(models.QuizSubmission).filter(
        models.QuizSubmission.quiz_id == quiz_id,
        models.QuizSubmission.user_id == current_user.id
    ).first()
    if already_submitted:
        raise HTTPException(status_code=400, detail="You have already submitted your response for this quiz!")

    quiz = db.query(models.GroupQuiz).filter(models.GroupQuiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz mission not found")

    is_correct_answer = 1 if submission_data.selected_option.upper() == quiz.correct_option.upper() else 0
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    new_submission = models.QuizSubmission(
        quiz_id=quiz_id,
        user_id=current_user.id,
        selected_option=submission_data.selected_option.upper(),
        is_correct=is_correct_answer,
        time_taken_seconds=submission_data.time_taken_seconds,
        submitted_at=now_str
    )
    db.add(new_submission)
    db.commit()

    progress = db.query(models.UserProgress).filter(models.UserProgress.user_id == current_user.id).first()
    if not progress:
        progress = models.UserProgress(user_id=current_user.id, xp=0, streak_count=0, last_active_date=None)
        db.add(progress)
    
    if is_correct_answer == 1:
        progress.xp += 10       
    else:
        progress.xp = max(0, progress.xp - 2) 
    db.commit()
    return {"status": "success", "is_correct": is_correct_answer == 1, "message": "Response tracked by the central server!"}


@app.get("/admin/quizzes/{quiz_id}/responses")
def get_quiz_responses(
    quiz_id: int,
    admin: models.User = Depends(get_admin_user), 
    db: Session = Depends(get_db)
):
    submissions = db.query(models.QuizSubmission).filter(models.QuizSubmission.quiz_id == quiz_id).all()
    report_card = []
    for sub in submissions:
        user_info = db.query(models.User).filter(models.User.id == sub.user_id).first()
        if user_info:
            report_card.append({
                "name": user_info.name,
                "username": user_info.username,
                "email": user_info.email,
                "selected_option": sub.selected_option,
                "verdict": "✅ Correct" if sub.is_correct == 1 else "❌ Wrong",
                "time_taken": f"{sub.time_taken_seconds} sec",
                "submitted_at": sub.submitted_at
            })
    return {"quiz_id": quiz_id, "total_responses": len(report_card), "results": report_card}


# LIVE BUG & FEEDBACK MONITOR 🐛
@app.post("/feedback")
def submit_user_feedback(
    feedback_data: dict, 
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    category = feedback_data.get("category", "suggestion").lower()
    message = feedback_data.get("message")
    if not message or len(message.strip()) == 0:
        raise HTTPException(status_code=400, detail="Feedback alert network requires content text!")

    if category not in ["bug", "glitch", "suggestion"]:
        raise HTTPException(status_code=400, detail="Invalid monitoring matrix category!")

    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    new_feedback = models.UserFeedback(
        user_id=current_user.id,
        category=category,
        message=message,
        created_at=now_str
    )
    db.add(new_feedback)
    db.commit()
    return {"status": "success", "message": "Telemetry feedback logged securely to the WAR Room!"}


@app.get("/admin/feedbacks")
def get_all_feedbacks(
    admin: models.User = Depends(get_admin_user), 
    db: Session = Depends(get_db)
):
    feedbacks = db.query(models.UserFeedback).order_by(models.UserFeedback.id.desc()).all()
    report = []
    for fb in feedbacks:
        user_info = db.query(models.User).filter(models.User.id == fb.user_id).first()
        if user_info:
            report.append({
                "name": user_info.name,
                "username": user_info.username,
                "category": fb.category,
                "message": fb.message,
                "created_at": fb.created_at
            })
    return {"total_feedbacks": len(report), "feedbacks": report}