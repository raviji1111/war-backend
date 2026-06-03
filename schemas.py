from pydantic import BaseModel
from typing import Optional

# ==========================================
# 1. USER & STUDY SCHEMAS
# ==========================================
class UserCreate(BaseModel):
    name: str        # NAYA: Frontend se name lega
    username: str    # NAYA: Frontend se unique User ID lega
    email: str
    password: str

# Rule for saving study time
class StudyRecord(BaseModel):
    duration_minutes: int
    date: str

# Rule for creating a Note
class NoteCreate(BaseModel):
    title: str
    content: str


# ==========================================
# 2. NEW: COMMUNITY & EXAM GROUPS SCHEMAS 🚀
# ==========================================

# Rule for creating a new Study Group
class GroupCreate(BaseModel):
    name: str
    description: str

# Rule for Admin posting a message or a PDF file link
class PostCreate(BaseModel):
    content: str
    file_url: Optional[str] = None  # Optional: Admin bina file ke bhi message bhej sakta hai


# ==========================================
# 3. NEW: QUIZ & QUESTIONS SCHEMAS 📝
# ==========================================

# Rule for creating a new Quiz
class QuizCreate(BaseModel):
    title: str

# Rule for adding an MCQ Question to a Quiz
class QuestionCreate(BaseModel):
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: str  # Only accepts 'A', 'B', 'C', or 'D'


# ==========================================
# 4. NAYA: LIVE GROUP QUIZ SCHEMA 🎯
# ==========================================
# Ye tumhare naye GroupQuiz model ke liye hai takki purana code disturb na ho!
class GroupQuizCreate(BaseModel):
    question: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str  # Only accepts 'A', 'B', 'C', or 'D'


    # Rule for submitting quiz answers from student side
class QuizSubmit(BaseModel):
    selected_option: str
    time_taken_seconds: int


    