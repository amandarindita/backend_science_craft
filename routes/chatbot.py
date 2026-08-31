import os
import fitz
from flask import Blueprint, request, jsonify
from services.key_rotator import KeyRotator

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

chatbot_bp = Blueprint('chatbot', __name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PATH = os.path.join(BASE_DIR, 'chroma_db')
DATASET_PATH = os.path.join(BASE_DIR, 'dataset')

vector_db = None

def get_vector_db():
    global vector_db
    if vector_db is not None:
        return vector_db

    try:
        embeddings = HuggingFaceEmbeddings(model_name='sentence-transformers/all-MiniLM-L6-v2')
        
        if os.path.exists(CHROMA_PATH) and len(os.listdir(CHROMA_PATH)) > 0:
            print('[RAG] Memuat Vector DB tersimpan dari disk...')
            vector_db = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
            print('[RAG] Vector DB siap (dimuat dari disk)!')
            return vector_db

        all_text = ''
        if os.path.isdir(DATASET_PATH):
            for filename in os.listdir(DATASET_PATH):
                if filename.endswith('.pdf'):
                    file_path = os.path.join(DATASET_PATH, filename)
                    print(f'[RAG] Membaca file PDF: {file_path}')
                    doc = fitz.open(file_path)
                    for page in doc:
                        all_text += page.get_text('text') + '\n'
        else:
            print(f'[RAG] Folder dataset tidak ditemukan di: {DATASET_PATH}')

        if all_text:
            print('[RAG] Memulai split text...')
            splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
            chunks = splitter.split_text(all_text)
            print('[RAG] Memulai embedding...')
            vector_db = Chroma.from_texts(chunks, embedding=embeddings, persist_directory=CHROMA_PATH) 
            print('[RAG] Vector DB siap dan berhasil disimpan ke disk!')
        else:
            print('[RAG] Tidak ada teks PDF. Chatbot jalan tanpa konteks.')

    except Exception as e:
        print(f'[RAG] Terjadi error saat inisialisasi: {e}')

    return vector_db

def ask_cheerful_scibot(question):
    context = ''
    try:
        db = get_vector_db()
        if db:
            retriever = db.as_retriever(search_kwargs={'k': 3}) 
            docs = retriever.invoke(question)
            context = '\n'.join([d.page_content for d in docs])
    except Exception as e:
        print(f'[RAG Warning] Gagal query retriever: {e}. Melanjutkan tanpa konteks.')
    
    prompt = (
        "Kamu adalah SENA (Science Education Navigator Assistant), "
        "asisten sains ceria dan edukatif untuk anak SMA.\n"
        "Jawablah dengan gaya ringan, bersemangat, dan mudah dipahami.\n\n"
        f"Gunakan konteks berikut JIKA ADA untuk membantu menjawab:\n{context}\n\n"
        f"Pertanyaan: {question}"
    )
    
    def _call(model):
        res = model.generate_content(prompt)
        return res.text

    return KeyRotator.call_gemini_rotator('gemini-2.5-flash', _call)

@chatbot_bp.route('', methods=['POST'])
@chatbot_bp.route('/', methods=['POST'])
def chat_gemini():
    data = request.get_json(silent=True) or {}
    user_message = data.get('message', '').strip()
    
    if not user_message: 
        return jsonify({'error': 'Pesan tidak boleh kosong'}), 400
        
    try:
        reply = ask_cheerful_scibot(user_message)
        return jsonify({'reply': reply})
    except Exception as e:
        print(f'[Chatbot Error]: {e}')
        return jsonify({'error': str(e)}), 500
