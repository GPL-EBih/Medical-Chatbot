import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY_ASSEMBLYAI = os.environ.get("API_KEY_ASSEMBLYAI")

if not API_KEY_ASSEMBLYAI:
    raise ValueError("Missing API_KEY_ASSEMBLYAI in .env file")

upload_endpoint = "https://api.assemblyai.com/v2/upload"
transcript_endpoint = "https://api.assemblyai.com/v2/transcript"
headers_auth_only = {"authorization": API_KEY_ASSEMBLYAI}
headers = {"authorization": API_KEY_ASSEMBLYAI, "content-type": "application/json"}

CHUNK_SIZE = 5_242_880  # 5MB

def upload(filename):
    def read_file(filename):
        with open(filename, "rb") as f:
            while True:
                data = f.read(CHUNK_SIZE)
                if not data:
                    break
                yield data

    response = requests.post(upload_endpoint, headers=headers_auth_only, data=read_file(filename))
    response.raise_for_status()
    return response.json()["upload_url"]

def transcribe(audio_url, language_code="en"):
    request_body = {"audio_url": audio_url, "language_code": language_code}
    response = requests.post(transcript_endpoint, json=request_body, headers=headers)
    response.raise_for_status()
    return response.json()["id"]

def poll(transcript_id):
    polling_endpoint = f"{transcript_endpoint}/{transcript_id}"
    while True:
        response = requests.get(polling_endpoint, headers=headers)
        response.raise_for_status()
        data = response.json()

        if data["status"] == "completed":
            return data
        elif data["status"] == "error":
            raise RuntimeError(data["error"])

        time.sleep(5)

def transcribe_file(filepath, language_code="en"):
    """Convenience function: upload -> transcribe -> poll -> return text"""
    audio_url = upload(filepath)
    transcript_id = transcribe(audio_url, language_code)
    result = poll(transcript_id)
    return result["text"]
