from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import pandas as pd
import json
from typing import List, Dict
import os
from datetime import datetime

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Database initialization
def init_db():
    conn = sqlite3.connect('mcq_exam.db')
    c = conn.cursor()
    
    # Create questions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS questions
        (id INTEGER PRIMARY KEY,
         question_text TEXT,
         option_a TEXT,
         option_b TEXT,
         option_c TEXT,
         option_d TEXT,
         correct_answer TEXT,
         exam_session_id INTEGER)
    ''')
    
    # Create exam_sessions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS exam_sessions
        (id INTEGER PRIMARY KEY,
         correct_marks FLOAT,
         negative_marks FLOAT,
         start_time TIMESTAMP,
         end_time TIMESTAMP,
         total_score FLOAT)
    ''')
    
    # Create user_responses table
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_responses
        (id INTEGER PRIMARY KEY,
         question_id INTEGER,
         exam_session_id INTEGER,
         selected_answer TEXT,
         is_correct BOOLEAN)
    ''')
    
    conn.commit()
    conn.close()

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()

@app.post("/upload-excel")
async def upload_excel(file: UploadFile = File(...)):
    try:
        # Save the file temporarily
        file_path = f"uploaded_files/{file.filename}"
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Read Excel file
        df = pd.read_excel(file_path)
        
        # Validate Excel structure
        required_columns = ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_answer']
        if not all(col in df.columns for col in required_columns):
            raise HTTPException(status_code=400, detail="Invalid Excel format. Required columns missing.")
        
        # Connect to database
        conn = sqlite3.connect('mcq_exam.db')
        c = conn.cursor()
        
        # Insert questions into database
        for index, row in df.iterrows():
            c.execute('''
                INSERT INTO questions (question_text, option_a, option_b, option_c, option_d, correct_answer)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                row['question_text'],
                row['option_a'],
                row['option_b'],
                row['option_c'],
                row['option_d'],
                row['correct_answer']
            ))
        
        conn.commit()
        conn.close()
        
        # Clean up uploaded file
        os.remove(file_path)
        
        return {"message": "File processed successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/exam-session")
async def create_exam_session(correct_marks: float, negative_marks: float):
    try:
        conn = sqlite3.connect('mcq_exam.db')
        c = conn.cursor()
        
        c.execute('''
            INSERT INTO exam_sessions (correct_marks, negative_marks, start_time)
            VALUES (?, ?, ?)
        ''', (correct_marks, negative_marks, datetime.now()))
        
        session_id = c.lastrowid
        conn.commit()
        conn.close()
        
        return {"session_id": session_id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/questions/{session_id}")
async def get_questions(session_id: int):
    try:
        conn = sqlite3.connect('mcq_exam.db')
        c = conn.cursor()
        
        # Get all questions and randomize them
        c.execute("SELECT id, question_text, option_a, option_b, option_c, option_d FROM questions ORDER BY RANDOM()")
        questions = c.fetchall()
        
        # Format questions
        formatted_questions = []
        for q in questions:
            formatted_questions.append({
                "id": q[0],
                "question_text": q[1],
                "options": [q[2], q[3], q[4], q[5]]
            })
        
        conn.close()
        return formatted_questions
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/submit-answer")
async def submit_answer(question_id: int, session_id: int, selected_answer: str):
    try:
        conn = sqlite3.connect('mcq_exam.db')
        c = conn.cursor()
        
        # Get correct answer
        c.execute("SELECT correct_answer FROM questions WHERE id = ?", (question_id,))
        correct_answer = c.fetchone()[0]
        
        # Check if answer is correct
        is_correct = selected_answer == correct_answer
        
        # Save response
        c.execute('''
            INSERT INTO user_responses (question_id, exam_session_id, selected_answer, is_correct)
            VALUES (?, ?, ?, ?)
        ''', (question_id, session_id, selected_answer, is_correct))
        
        conn.commit()
        conn.close()
        
        return {"message": "Answer submitted successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/end-exam/{session_id}")
async def end_exam(session_id: int):
    try:
        conn = sqlite3.connect('mcq_exam.db')
        c = conn.cursor()
        
        # Get exam session details
        c.execute("SELECT correct_marks, negative_marks FROM exam_sessions WHERE id = ?", (session_id,))
        session = c.fetchone()
        correct_marks, negative_marks = session
        
        # Calculate total score
        c.execute("SELECT COUNT(*) FROM user_responses WHERE exam_session_id = ? AND is_correct = 1", (session_id,))
        correct_count = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM user_responses WHERE exam_session_id = ? AND is_correct = 0", (session_id,))
        incorrect_count = c.fetchone()[0]
        
        total_score = (correct_count * correct_marks) - (incorrect_count * negative_marks)
        
        # Update exam session
        c.execute('''
            UPDATE exam_sessions 
            SET end_time = ?, total_score = ?
            WHERE id = ?
        ''', (datetime.now(), total_score, session_id))
        
        conn.commit()
        conn.close()
        
        return {
            "total_score": total_score,
            "correct_answers": correct_count,
            "incorrect_answers": incorrect_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
