# import some important libraries
import os

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from firebase_service import get_favorites, toggle_favorite
from google import genai
from pydantic import BaseModel

load_dotenv() 

# define some of our constants
GEMINI_MODEL = "gemini-3.5-flash-lite"
ELEVENLABS_MODEL = "eleven_multilingual_v2"
ELEVENLABS_STT_MODEL = "scribe_v2"

# create our fast api app 
app = FastAPI(title="Chef Voice Backend") # this line wont be here in hacker version

# need this so our frontend and backend can talk to each other
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# code health endpoint here:
# to test if our backend is running
@app.get("/health")
def health():
    return {"status": "ok"}


# helper function to generate a chef-like reply using Gemini API
def make_chef_reply(user_text: str, gemini_api_key: str) -> str:
    prompt = (
        "You are a distinguished chef with a quirky sense of humor. Listen for a user's cooking question or request.  "
        "Always be very concise: answer in 1 to 2 short sentences max. "
        "Focus on practical cooking help. "
        "Use simple words, light humor, and occasional clever rmarks "
        "Do not use markdown, lists, or long explanations. "
        f"User: {user_text}"
    )

    # code gemini api call here: 
    try:
        client = genai.Client(api_key=gemini_api_key)
        gemini_response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        reply_text = gemini_response.text.strip()
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Gemini request failed: {error}")

    if not reply_text:
        raise HTTPException(status_code=502, detail="Gemini returned no text")

    return reply_text

# function to make audio from the chef reply using ElevenLabs API
def make_audio(reply_text: str, elevenlabs_api_key: str, voice_id: str) -> bytes:
    # code elevenlabs text-to-speech API call here:
    elevenlabs_response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{hpp4J3VqNfWAUOO0d1Us}",
        headers={
            "xi-api-key": elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json={
            "text": reply_text,
            "model_id": ELEVENLABS_MODEL,
        },
        timeout=300,
    )
    # end of elevenlabs text-to-speech API call

    # if there is an erorr we will return a 502 error to the frontend
    if elevenlabs_response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"ElevenLabs audio generation failed: {elevenlabs_response.text}",
        )

    return elevenlabs_response.content


# function to transcribe audio using ElevenLabs API

def transcribe_audio(file: UploadFile, elevenlabs_api_key: str) -> str:
    audio_bytes = file.file.read() # file is an object which has a file attribute, read bytes with .read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty")

    # code elevenlabs speech-to-text API call here:
    stt_response = requests.post(
        "https://api.elevenlabs.io/v1/speech-to-text",
        headers={"xi-api-key": elevenlabs_api_key},
        files={
            "file": (
                file.filename or "recording.webm",
                audio_bytes,
                file.content_type or "audio/webm",
            )
        },
        data={"model_id": ELEVENLABS_STT_MODEL},
        timeout=300,
    )
    # end of elevenlabs speech-to-text API call

    # check if the transcription was successful
    if stt_response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"ElevenLabs transcription failed: {stt_response.text}",
        )

    # get transcript from the response
    transcript = stt_response.json().get("text", "").strip()
    if not transcript:
        raise HTTPException(status_code=502, detail="ElevenLabs returned no transcript")

    return transcript


# to generate a chef-like voice from an audio file
@app.post("/chef/voice/audio")
def create_chef_voice_from_audio(file: UploadFile = File(...)):
    # code here
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")

    # code here : if missing some of our API keys, return an error
    if not gemini_api_key:
        raise HTTPException(status_code=500, detail="Missing Gemini API key")
    if not elevenlabs_api_key or not voice_id:
        raise HTTPException(status_code=500, detail="Missing ElevenLabs API key or voice ID")

    # code here
    # call our helper functions
    transcript = transcribe_audio(file, elevenlabs_api_key)
    reply_text = make_chef_reply(transcript, gemini_api_key)
    audio_bytes = make_audio(reply_text, elevenlabs_api_key, voice_id)

    # return our audio
    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
    )


#add request models here: 
# make a model for food items for the favorites endpoint:
class FoodItem(BaseModel):
    id: int
    name: str
    emoji: str
    description: str
    cookTime: int
    difficulty: str
    ingredients: list[str]
    instructions: list[str]

# make a model for favorite requests for the favorites endpoint:
class FavoriteRequest(BaseModel):
    userId: str
    food: FoodItem

#code get favorites endpoint here:
@app.get("/favorites/{user_id}")
def get_user_favorites(user_id: str):
    return {"favorites": get_favorites(user_id)}


# make endpoint for toggling user favorites
@app.post("/favorites/toggle")
def toggle_user_favorite(request: FavoriteRequest):
    updated_favorites = toggle_favorite(
        request.userId,
        request.food.model_dump(exclude_none=True),
    )

    return {"favorites": updated_favorites}
