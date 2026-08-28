import os
import fitz
from flask import Blueprint, request, jsonify
import google.generativeai as genai

# Import untuk LangChain RAG
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

chatbot_bp = Blueprint('chatbot', __name__)

# --- KONFIGURASI GEMINI ---
genai.configure(api_key=os.environ.get('GEMINI_API_KEY')) 
model = genai.GenerativeModel('gemini-2.5-flash')

# --- INISIALISASI RAG (LAZY LOADING & PERSISTENSI) ---
vector_db = None
CHROMA_PATH = "chroma_db"

def get_vector_db():
    global vector_db
    if vector_db is not None:
        return vector_db

    try:
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        
        # Cek apakah Vector DB sudah pernah disimpan di disk
        if os.path.exists(CHROMA_PATH) and len(os.listdir(CHROMA_PATH)) > 0:
            print("Memuat Vector DB tersimpan dari disk...")
            vector_db = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
            print("Vector DB siap (dimuat dari disk)!")
            return vector_db

        # Jika belum ada, baca PDF & buat database baru
        folder_path = "dataset"
        all_text = ""
        if os.path.isdir(folder_path):
            for filename in os.listdir(folder_path):
                if filename.endswith(".pdf"):
                    file_path = os.path.join(folder_path, filename)
                    print(f"Membaca file: {file_path}")
                    doc = fitz.open(file_path)
                    for page in doc:
                        all_text += page.get_text("text") + "\n"
        else:
            print(f"Error: Folder '{folder_path}' tidak ditemukan.")

        if all_text:
            print("Memulai split text...")
            splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
            chunks = splitter.split_text(all_text)
            print("Memulai embedding...")
            vector_db = Chroma.from_texts(chunks, embedding=embeddings, persist_directory=CHROMA_PATH) 
            print("Vector DB siap dan berhasil disimpan ke disk!")
        else:
            print("Tidak ada teks PDF. Chatbot jalan tanpa konteks.")

    except Exception as e:
        print(f"Terjadi error saat inisialisasi RAG: {e}")

    return vector_db


# --- LOGIKA CHATBOT SENA ---
def ask_cheerful_scibot(question):
    db = get_vector_db()
    context = ""
    if db:
        # Cari 3 chunk teks yang paling relevan dari PDF
        retriever = db.as_retriever(search_kwargs={"k": 3}) 
        docs = retriever.invoke(question)
        context = "\n".join([d.page_content for d in docs])
    
    prompt = f"""
    Kamu adalah SENA (Science Education Navigator Assistant),
    asisten sains ceria dan edukatif untuk anak SMA.
    Jawablah dengan gaya ringan, bersemangat, dan mudah dipahami.

    Gunakan konteks berikut JIKA ADA untuk membantu menjawab:
    {context}

    Pertanyaan: {question}
    """
    response = model.generate_content(prompt) 
    return response.text


@chatbot_bp.route('', methods=['POST'])
def chat_gemini():
    data = request.get_json()
    user_message = data.get('message', '')
    
    if not user_message: 
        return jsonify({"error": "Pesan tidak boleh kosong"}), 400
        
    try:
        reply = ask_cheerful_scibot(user_message)
        return jsonify({"reply": reply})
    except Exception as e:
        print(f"Error di /chat/gemini: {e}")
        return jsonify({"error": str(e)}), 500