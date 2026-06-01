from sqlalchemy import Column, Integer, String, ForeignKey, Text  # 🔥 FIXED: Text import yahan jod diya hai
from database import Base

# ==========================================
# 1. CORE USER SYSTEM
# ==========================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True) # Unique User ID feature
    name = Column(String)                              # Full Name feature
    hashed_password = Column(String)
    is_active = Column(Integer, default=1)


# ==========================================
# 2. STUDY TRACKING SYSTEM
# ==========================================
class StudySession(Base):
    __tablename__ = "study_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id")) 
    duration_minutes = Column(Integer)                
    date = Column(String)                             


# ==========================================
# 3. PERSONAL NOTES SYSTEM
# ==========================================
class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id")) 
    title = Column(String)
    content = Column(String)


# ==========================================
# 4. NEW: COMMUNITY & EXAM GROUPS SYSTEM 🚀
# ==========================================

# Groups (Jaise WhatsApp ya Telegram group hota hai)
class ExamGroup(Base):
    __tablename__ = "exam_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)       # Group ka naam
    description = Column(String)            # Group kis exam ke liye hai


# Members of the Group (Kaun Admin hai, kaun Student)
class GroupMembership(Base):
    __tablename__ = "group_memberships"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("exam_groups.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String, default="member") # Role "admin" ya "member" ho sakta hai


# Posts & Files (Admin yahan PDFs aur Important Info dega)
class GroupPost(Base):
    __tablename__ = "group_posts"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("exam_groups.id"))
    author_id = Column(Integer, ForeignKey("users.id")) # Jisne bheja (Usually Admin)
    content = Column(String)                # Message ya Text
    file_url = Column(String, nullable=True)# PDF ya Image ka link (Agar kuch bheja toh)
    created_at = Column(String)             # Kab post hua


# ==========================================
# 5. NEW: QUIZ & QUESTIONS SYSTEM 📝
# ==========================================

# Quiz banayenge groups ke andar
class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("exam_groups.id"))
    title = Column(String)                  # e.g., "Python Mega Test 1"


# Quiz ke questions (A, B, C, D options ke sath)
class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"))
    question_text = Column(String)
    option_a = Column(String)
    option_b = Column(String)
    option_c = Column(String)
    option_d = Column(String)
    correct_answer = Column(String)         # 'A', 'B', 'C', ya 'D'


# FIXED & ADDED: Live Group Quiz Model with Answer Key 🎯
class GroupQuiz(Base):
    __tablename__ = "group_quizzes"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, index=True)
    question = Column(String, nullable=False)
    option_a = Column(String, nullable=False)
    option_b = Column(String, nullable=False)
    option_c = Column(String, nullable=False)
    option_d = Column(String, nullable=False)
    correct_option = Column(String, nullable=False) # Isme 'A', 'B', 'C', ya 'D' save hoga


# ==========================================
# 6. NAYA: QUIZ SUBMISSION TRACKER 📊
# ==========================================
class QuizSubmission(Base):
    __tablename__ = "quiz_submissions"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    selected_option = Column(String, nullable=False)   # Bache ne kya choose kiya ('A', 'B' etc.)
    is_correct = Column(Integer, default=0)            # 1 = Sahi, 0 = Galat
    time_taken_seconds = Column(Integer)               # Kitne time me kiya (in seconds)
    submitted_at = Column(String)                      # Exact date aur time


# ==========================================
# 7. GAMIFICATION TRACKER (XP & STREAKS) 🔥
# ==========================================
class UserProgress(Base):
    __tablename__ = "user_progress"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    xp = Column(Integer, default=0)
    streak_count = Column(Integer, default=0)
    last_active_date = Column(String, nullable=True) # Format: YYYY-MM-DD


# ==========================================
# 8. LIVE BUG & FEEDBACK MONITOR 🐛
# ==========================================
class UserFeedback(Base):
    __tablename__ = "user_feedbacks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    category = Column(String, nullable=False) # 'bug', 'glitch', 'suggestion'
    message = Column(Text, nullable=False)
    created_at = Column(String)