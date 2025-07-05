import os
import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import json
import base64

load_dotenv()

DB_DOCS_LIMIT = 10  # Maximum number of documents allowed in the database

# Initialize session state variables
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "username" not in st.session_state:
    st.session_state.username = ""
if "password" not in st.session_state:
    st.session_state.password = ""

# FastAPI backend URL
API_URL = os.getenv("API_URL", "http://localhost:8000")


def login(username: str, password: str) -> bool:
    """Attempt to log in to the FastAPI backend."""
    try:
        login_endpoint = API_URL + "/login"
        response = requests.post(
            login_endpoint,
            json={"username": username, "password": password},
            auth=HTTPBasicAuth(username, password),
            timeout=5,
        )
        if response.status_code == 200:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.password = password

            # Extract session_id from response.text
            try:
                response_json = json.loads(response.text)
                session_id = response_json.get("session_id", None)
                if session_id:
                    st.session_state.session_id = session_id
                else:
                    st.error("Session ID not found in response.")
                    return False
            except json.JSONDecodeError:
                st.error("Failed to parse login response.")
                return False
            return True
        else:
            st.error("Incorrect username or password")
            return False
    except requests.RequestException as e:
        st.error(f"Failed to connect to the backend: {e}")
        return False


def send_message(message: str):
    """Send a message to the FastAPI backend and stream the response with markdown formatting, including images."""
    try:
        chat_endpoint = API_URL + "/chat"
        with requests.post(
            chat_endpoint,
            json={"message": message, "session_id": st.session_state.session_id},
            auth=HTTPBasicAuth(st.session_state.username, st.session_state.password),
            timeout=120,  # Increased timeout for potentially longer image generation
            stream=True,
        ) as response:
            if response.status_code == 200:
                response_chunks = []
                response_placeholder = st.empty()  # Placeholder for streamed content

                buffer = b""
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        buffer += chunk
                        try:
                            # Try to decode and parse the buffer as JSON
                            chunk_data = json.loads(buffer.decode("utf-8"))
                            response_chunks.append(chunk_data)
                            buffer = b""  # Clear buffer after successful parse

                            # Display content as it streams
                            with response_placeholder.container():
                                for item in response_chunks:
                                    if item["type"] == "text":
                                        st.markdown(item["content"])
                                    if item["type"] == "image":
                                        caption_text = item.get(
                                            "alt_text", "Generated Image"
                                        )  # Use alt_text if available
                                        st.image(
                                            base64.b64decode(item["content"]),
                                            caption=caption_text,
                                        )
                        except json.JSONDecodeError:
                            # Wait for more data in buffer
                            continue
                # After streaming, if buffer is not empty, try one last parse
                if buffer:
                    try:
                        chunk_data = json.loads(buffer.decode("utf-8"))
                        response_chunks.append(chunk_data)
                        with response_placeholder.container():
                            for item in response_chunks:
                                if item["type"] == "text":
                                    st.markdown(item["content"])
                                if item["type"] == "image":
                                    caption_text = item.get(
                                        "alt_text", "Generated Image"
                                    )
                                    st.image(
                                        base64.b64decode(item["content"]),
                                        caption=caption_text,
                                    )
                    except json.JSONDecodeError:
                        st.warning(
                            "Received malformed JSON chunk at end of stream. Skipping."
                        )

                # Store the complete parsed history
                st.session_state.chat_history.append(
                    {
                        "role": "assistant",
                        "content": response_chunks,  # Store as list of dicts
                        "username": st.session_state.username,
                    }
                )
            else:
                st.error(
                    f"Failed to send message: {response.status_code} - {response.text}"
                )
    except requests.RequestException as e:
        st.error(f"Error communicating with backend: {e}")


def index_documents():
    """Trigger document indexing via the FastAPI backend."""
    try:
        index_endpoint = API_URL + "/index"
        response = requests.post(
            index_endpoint,
            auth=HTTPBasicAuth(st.session_state.username, st.session_state.password),
            timeout=500,
        )
        if response.status_code == 200:
            response_data = response.json()
            st.success(f"{response_data['message']}")
        else:
            st.error("Failed to index documents. Please try again.")

        st.session_state.rag_sources = get_rag_files()
    except requests.RequestException as e:
        st.error(f"Error communicating with backend: {e}")


def reset_session_id():
    """Reset the session ID in the session state."""
    response = requests.post(
        API_URL + "/session_id",
        auth=HTTPBasicAuth(st.session_state.username, st.session_state.password),
        timeout=50,
    )
    if response.status_code == 200:
        new_session_id = response.json().get("session_id", None)
        if new_session_id:
            st.session_state.session_id = new_session_id
        st.success(f"Session ID reset to: {new_session_id}")
    else:
        st.error("Failed to reset session ID.")


def reset_chat_history():
    """Clear the chat history."""
    st.session_state.chat_history = []
    st.success("Chat history cleared!")
    reset_session_id()


def get_rag_files():
    """Fetch the list of RAG sources from the FastAPI backend."""
    try:
        sources_endpoint = API_URL + "/rag_sources"
        response = requests.get(
            sources_endpoint,
            auth=HTTPBasicAuth(st.session_state.username, st.session_state.password),
            timeout=10,
        )
        if response.status_code == 200:
            return set(response.json().get("sources", []))
        else:
            st.error("Failed to fetch RAG sources.")
            return set()
    except requests.RequestException as e:
        st.error(f"Error fetching RAG sources: {e}")
        return set()


def load_doc_to_db():
    # Use loader according to doc type
    if "rag_docs" in st.session_state and st.session_state.rag_docs:
        if "rag_sources" not in st.session_state:
            st.session_state.rag_sources = set()
        for doc_file in st.session_state.rag_docs:
            if doc_file.name not in st.session_state.rag_sources:
                if len(st.session_state.rag_sources) < DB_DOCS_LIMIT:
                    os.makedirs("source_files", exist_ok=True)
                    file_path = f"./source_files/{doc_file.name}"
                    try:
                        # Save uploaded file to disk
                        with open(file_path, "wb") as f:
                            f.write(doc_file.getbuffer())
                        # Send file to backend
                        with open(file_path, "rb") as f:
                            files = {"file": (doc_file.name, f, doc_file.type)}
                            response = requests.post(
                                API_URL + "/upload_files",
                                files=files,
                                auth=HTTPBasicAuth(
                                    st.session_state.username, st.session_state.password
                                ),
                                timeout=120,
                            )
                        if response.status_code == 200:
                            st.success(f"Uploaded and indexed: {doc_file.name}")
                            st.session_state.rag_sources.add(doc_file.name)
                        else:
                            st.error(
                                f"Failed to upload {doc_file.name}: {response.text}"
                            )
                    except Exception as e:
                        st.error(f"Error uploading {doc_file.name}: {e}")
                    finally:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                else:
                    st.error(f"Maximum number of documents reached ({DB_DOCS_LIMIT}).")


# Streamlit app layout
st.title("Advanced RAG Chatbot")

# Sidebar for reset button
with st.sidebar:

    if st.session_state.logged_in:

        st.session_state.rag_sources = get_rag_files()

        st.write(f"Logged in as: {st.session_state.username}")
        if st.button("Reset Chat History"):
            reset_chat_history()
        if st.button("Re-Index Documents"):
            index_documents()

        # File upload input for RAG with documents
        # File uploader with RAG sources as help text

        st.file_uploader(
            "📄 Upload a document",
            type=["pdf", "txt", "docx", "md", "csv", "json"],
            accept_multiple_files=True,
            on_change=load_doc_to_db,
            key="rag_docs",
        )
        if "rag_sources" in st.session_state and st.session_state.rag_sources:
            st.markdown("**Current RAG Sources:**")
            for src in st.session_state.rag_sources:
                cols = st.columns([0.6, 0.4])
                with cols[0]:
                    st.markdown(f"- {src}")
                with cols[1]:
                    if st.button("Delete", key=f"delete_{src}"):
                        try:
                            delete_endpoint = API_URL + "/delete_rag_source"
                            response = requests.post(
                                delete_endpoint,
                                json={"filename": src},
                                auth=HTTPBasicAuth(
                                    st.session_state.username, st.session_state.password
                                ),
                                timeout=30,
                            )

                            if response.status_code == 200:
                                st.success(f"Deleted: {src}")
                                st.session_state.rag_sources.remove(src)
                                st.rerun()
                            else:
                                st.error(f"Failed to delete {src}: {response.text}")

                            st.session_state.rag_sources = get_rag_files()
                        except Exception as e:
                            st.error(f"Error deleting {src}: {e}")
        else:
            st.markdown("**No RAG sources found.**")

# Login page
if not st.session_state.logged_in:
    st.subheader("Login")
    username_input = st.text_input("Username", key="username_input")
    password_input = st.text_input("Password", type="password", key="password_input")
    if st.button("Login"):
        if login(username_input, password_input):
            st.rerun()
else:
    # Chat interface
    st.subheader("Chat Window")

    # Display chat history
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    st.markdown(message["content"])
                else:
                    # Assistant message can be a list of content blocks
                    for item in message["content"]:
                        if item["type"] == "text":
                            st.markdown(item["content"])
                        elif item["type"] == "image":
                            image_bytes = base64.b64decode(item["content"])
                            st.image(
                                image_bytes,
                                caption="Generated Diagram/Image",
                                use_column_width=True,
                            )

    # Chat input at the bottom
    if user_text := st.chat_input("Type your message and hit Enter…"):
        st.session_state.chat_history.append({"role": "user", "content": user_text})
        with st.chat_message("user"):
            st.markdown(user_text)

        send_message(user_text)
        st.rerun()
