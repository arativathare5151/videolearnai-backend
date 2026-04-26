from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from config import settings
from db import db_insert, db_update, db_select
import ffmpeg
import tempfile
import os
import uuid
import json
import time
from groq import Groq

router = APIRouter()

# Init Groq client
groq_client = Groq(api_key=settings.GROQ_API_KEY)


def ask_groq(prompt: str) -> str:
    """Call Groq API with llama model"""
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=2048,
    )
    return response.choices[0].message.content


@router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    user_id: str = Form(...),
):
    tmp_video_path = None
    tmp_audio_path = None
    video_id = None

    try:
        # 1. Save uploaded file temporarily
        suffix = os.path.splitext(file.filename)[1] or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_video_path = tmp.name

        # 2. Save video record to Supabase
        video_id = str(uuid.uuid4())
        await db_insert("videos", {
            "id": video_id,
            "user_id": user_id,
            "title": title,
            "description": description,
            "status": "processing",
        })

        # 3. Extract audio using FFmpeg
        tmp_audio_path = tmp_video_path.replace(suffix, ".wav")
        (
            ffmpeg
            .input(tmp_video_path)
            .output(tmp_audio_path, ar=16000, ac=1, format="wav")
            .overwrite_output()
            .run(quiet=True)
        )

        # 4. Transcribe using Groq Whisper API
        with open(tmp_audio_path, "rb") as audio_file:
            transcription = groq_client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=audio_file,
            )
        transcript_text = transcription.text
        if not transcript_text.strip():
            transcript_text = "No speech detected in this video."

        # 5. Save transcript
        await db_insert("transcripts", {
            "video_id": video_id,
            "content": transcript_text,
            "status": "completed",
        })

        # 6. Generate summary with Groq
        time.sleep(1)
        summary = ask_groq(
            f"Summarize this educational video transcript in 3-4 sentences:\n\n{transcript_text[:4000]}"
        )

        # 7. Generate key topics with Groq
        time.sleep(1)
        topics_raw = ask_groq(
            f"List 5 key topics from this transcript as a JSON array of strings. "
            f"Return ONLY the JSON array, no markdown, no explanation:\n\n{transcript_text[:4000]}"
        )
        try:
            clean_topics = topics_raw.strip().strip("```json").strip("```").strip()
            key_topics = json.loads(clean_topics)
        except:
            key_topics = ["Topic 1", "Topic 2", "Topic 3", "Topic 4", "Topic 5"]

        # 8. Save quiz record
        quiz_id = str(uuid.uuid4())
        await db_insert("quizzes", {
            "id": quiz_id,
            "video_id": video_id,
            "title": f"Quiz: {title}",
            "summary": summary,
            "key_topics": key_topics,
            "status": "generating",
        })

        # 9. Generate quiz questions with Groq
        time.sleep(1)
        questions_raw = ask_groq(f"""Generate 5 multiple choice questions from this educational transcript.
Return ONLY a JSON array, no markdown, no explanation, just the array:
[
  {{
    "question_text": "...",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "correct_answer": "A",
    "explanation": "Brief explanation"
  }}
]
Transcript: {transcript_text[:3000]}""")

        try:
            clean_q = questions_raw.strip().strip("```json").strip("```").strip()
            questions = json.loads(clean_q)
        except:
            questions = [{
                "question_text": "What is the main topic of this video?",
                "options": [
                    "A. " + (key_topics[0] if key_topics else "Topic 1"),
                    "B. " + (key_topics[1] if len(key_topics) > 1 else "Topic 2"),
                    "C. " + (key_topics[2] if len(key_topics) > 2 else "Topic 3"),
                    "D. None of the above"
                ],
                "correct_answer": "A",
                "explanation": "This is the primary subject covered in the video."
            }]

        # 10. Save questions
        for i, q in enumerate(questions):
            await db_insert("quiz_questions", {
                "quiz_id": quiz_id,
                "question_text": q.get("question_text", ""),
                "options": q.get("options", []),
                "correct_answer": q.get("correct_answer", "A"),
                "explanation": q.get("explanation", ""),
                "order_index": i,
            })

        # 11. Update statuses to ready
        await db_update("quizzes", {"status": "ready"}, {"id": quiz_id})
        await db_update("videos", {"status": "ready"}, {"id": video_id})

        # 12. Cleanup temp files
        if tmp_video_path and os.path.exists(tmp_video_path):
            os.unlink(tmp_video_path)
        if tmp_audio_path and os.path.exists(tmp_audio_path):
            os.unlink(tmp_audio_path)

        return {
            "success": True,
            "video_id": video_id,
            "quiz_id": quiz_id,
            "transcript_preview": transcript_text[:300],
            "summary": summary,
            "key_topics": key_topics,
            "questions_count": len(questions),
        }

    except Exception as e:
        if tmp_video_path and os.path.exists(tmp_video_path):
            try: os.unlink(tmp_video_path)
            except: pass
        if tmp_audio_path and os.path.exists(tmp_audio_path):
            try: os.unlink(tmp_audio_path)
            except: pass
        if video_id:
            try:
                await db_update("videos", {"status": "error"}, {"id": video_id})
            except: pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}")
async def get_user_videos(user_id: str):
    try:
        videos = await db_select("videos", {"user_id": user_id})
        return {"videos": videos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{video_id}")
async def get_video(video_id: str):
    try:
        videos = await db_select("videos", {"id": video_id})
        if not videos:
            raise HTTPException(status_code=404, detail="Video not found")
        return videos[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))