import os
from openai import OpenAI
from dotenv import load_dotenv
import uuid

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def text_to_speech(text, output_dir="static/audio"):
    """
    Convert chatbot text to speech using OpenAI TTS
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        filename = f"response_{uuid.uuid4().hex}.mp3"
        output_path = os.path.join(output_dir, filename)

        with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text
        ) as response:
            response.stream_to_file(output_path)

        return "/" + output_path.replace("\\", "/")
    except Exception as e:
        print("Error in TTS:", e)
        return None
