# from flask import Flask, render_template, jsonify, request
# from src.helper import download_hugging_face_embeddings
# from langchain_pinecone import PineconeVectorStore
# from langchain_openai import ChatOpenAI
# from langchain.chains import create_retrieval_chain
# from langchain.chains.combine_documents import create_stuff_documents_chain
# from langchain_core.prompts import ChatPromptTemplate
# from dotenv import load_dotenv
# from src.prompt import *
# from src import speech
# from src import text_to_speech_service
# import os

# app = Flask(__name__)

# # Load API keys
# load_dotenv()
# PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
# OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY
# os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# os.environ["LANGCHAIN_TRACING_V2"] = "true"
# os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")
# os.environ["LANGCHAIN_PROJECT"] = "medical-chatbot"


# # Setup embeddings + retriever
# embeddings = download_hugging_face_embeddings()
# index_name = "medical-chatbot"
# docsearch = PineconeVectorStore.from_existing_index(
#     index_name=index_name,
#     embedding=embeddings
# )
# retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})

# chatModel = ChatOpenAI(model="gpt-4o")
# prompt = ChatPromptTemplate.from_messages(
#     [
#         ("system", system_prompt),
#         ("human", "{input}"),
#     ]
# )
# question_answer_chain = create_stuff_documents_chain(chatModel, prompt)
# rag_chain = create_retrieval_chain(retriever, question_answer_chain)

# @app.route("/")
# def index():
#     return render_template("chat.html")

# @app.route("/get", methods=["POST"])
# def chat():
#     msg = request.form["msg"]
#     mute = request.form.get("mute", "false")  # mute or unmute

#     # Get chatbot answer
#     response = rag_chain.invoke({"input": msg})
#     answer = str(response["answer"])

#     audio_url = None
#     if mute == "false":  # only generate TTS if unmuted
#         audio_url = text_to_speech_service.text_to_speech(answer)

#     return jsonify({"answer": answer, "audio_url": audio_url})

# @app.route("/speech", methods=["POST"])
# def speech_to_text():
#     if "audio" not in request.files:
#         return jsonify({"error": "No audio file uploaded"}), 400

#     file = request.files["audio"]
#     filepath = "temp_audio.wav"
#     file.save(filepath)

#     try:
#         transcript = speech.transcribe_file(filepath, language_code="en")
#         return jsonify({"transcript": transcript})
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500
#     finally:
#         if os.path.exists(filepath):
#             os.remove(filepath)

# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=8080, debug=True)


from flask import Flask, render_template, jsonify, request, session, redirect, url_for, flash
from flask_session import Session
from dotenv import load_dotenv
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid, os

# LangChain
from src.helper import download_hugging_face_embeddings
from langchain_pinecone import PineconeVectorStore
from langchain_openai import ChatOpenAI
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from src.prompt import *
from src import speech
from src import text_to_speech_service

# Flask app
app = Flask(__name__)
load_dotenv()
app.secret_key = os.getenv("SECRET_KEY", "supersecret")
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# MongoDB Atlas
mongo_client = MongoClient(os.getenv("MONGO_URI"))
db = mongo_client["medical_chatbot"]
users_col = db["users"]
history_col = db["chat_history"]

# LangChain setup
embeddings = download_hugging_face_embeddings()
index_name = "medical-chatbot"
docsearch = PineconeVectorStore.from_existing_index(index_name=index_name, embedding=embeddings)
retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})
chatModel = ChatOpenAI(model="gpt-4o")
prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", "{input}")])
qa_chain = create_stuff_documents_chain(chatModel, prompt)
rag_chain = create_retrieval_chain(retriever, qa_chain)

# ================= AUTH =================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        if users_col.find_one({"email": email}):
            flash("Email đã tồn tại!", "danger")
            return redirect(url_for("register"))
        hashed_pw = generate_password_hash(password)
        users_col.insert_one({"name": name, "email": email, "password": hashed_pw})
        flash("Đăng ký thành công! Hãy đăng nhập.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = users_col.find_one({"email": email})
        if user and check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            session["name"] = user["name"]
            return redirect(url_for("index"))
        else:
            flash("Sai email hoặc mật khẩu!", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Đã đăng xuất!", "info")
    return redirect(url_for("login"))

# ================= CHAT =================
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("chat.html", name=session.get("name"))

@app.route("/get", methods=["POST"])
def chat():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    msg = request.form["msg"]
    mute = request.form.get("mute", "false")
    session_id = session.get("session_id", str(uuid.uuid4()))
    session["session_id"] = session_id

    history_col.insert_one({
        "user_id": session["user_id"],
        "session_id": session_id,
        "role": "user",
        "message": msg,
        "timestamp": datetime.utcnow()
    })

    response = rag_chain.invoke({"input": msg})
    answer = str(response["answer"])

    history_col.insert_one({
        "user_id": session["user_id"],
        "session_id": session_id,
        "role": "bot",
        "message": answer,
        "timestamp": datetime.utcnow()
    })

    audio_url = None
    if mute == "false":
        audio_url = text_to_speech_service.text_to_speech(answer)

    return jsonify({"answer": answer, "audio_url": audio_url, "session_id": session_id})

@app.route("/history/list")
def history_list():
    if "user_id" not in session:
        return jsonify([])
    chats = history_col.find({"user_id": session["user_id"]}).sort("timestamp", 1)
    sessions = {}
    for c in chats:
        sid = c["session_id"]
        if sid not in sessions:
            sessions[sid] = c["timestamp"]
    result = [{"session_id": sid, "started_at": str(sessions[sid])} for sid in sessions]
    return jsonify(result)

@app.route("/history/<session_id>")
def history_detail(session_id):
    if "user_id" not in session:
        return jsonify([])
    chats = history_col.find({"user_id": session["user_id"], "session_id": session_id}).sort("timestamp", 1)
    result = [{"role": c["role"], "message": c["message"], "timestamp": str(c["timestamp"])} for c in chats]
    return jsonify(result)

@app.route("/history/<session_id>/delete", methods=["DELETE"])
def history_delete(session_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    history_col.delete_many({"user_id": session["user_id"], "session_id": session_id})
    return jsonify({"status": "deleted"})

# ================= SPEECH =================
@app.route("/speech", methods=["POST"])
def speech_to_text():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file uploaded"}), 400
    file = request.files["audio"]
    filepath = "temp_audio.wav"
    file.save(filepath)
    try:
        transcript = speech.transcribe_file(filepath, language_code="en")
        return jsonify({"transcript": transcript})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
