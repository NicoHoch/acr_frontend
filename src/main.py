import os
import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

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
            return True
        else:
            st.error("Incorrect username or password")
            return False
    except requests.RequestException as e:
        st.error(f"Failed to connect to the backend: {e}")
        return False


def send_message(message: str):
    """Send a message to the FastAPI backend and store the response."""
    try:
        chat_endpoint = API_URL + "/chat"
        response = requests.post(
            chat_endpoint,
            json={"message": message},
            auth=HTTPBasicAuth(st.session_state.username, st.session_state.password),
            timeout=5,
        )
        if response.status_code == 200:
            response_data = response.json()
            st.session_state.chat_history.append({"role": "user", "content": message})
            st.session_state.chat_history.append(
                {
                    "role": "assistant",
                    "content": response_data["message"],
                    "username": response_data["username"],
                }
            )
        else:
            st.error("Failed to send message. Please try again.")
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
            st.success(
                f"Document indexing completed successfully! {response_data['message']}"
            )
        else:
            st.error("Failed to index documents. Please try again.")
    except requests.RequestException as e:
        st.error(f"Error communicating with backend: {e}")


def reset_chat_history():
    """Clear the chat history."""
    st.session_state.chat_history = []
    st.success("Chat history cleared!")


# Streamlit app layout
st.title("Advanced RAG Chatbot")

# Sidebar for reset button
with st.sidebar:
    if st.session_state.logged_in:
        st.write(f"Logged in as: {st.session_state.username}")
        if st.button("Reset Chat History"):
            reset_chat_history()
        if st.button("Index Documents"):
            index_documents()

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
                    st.markdown(
                        f"**{message['username']} (Server):** {message['content']}"
                    )

    # Chat input at the bottom
    if user_text := st.chat_input("Type your message and hit Enter…"):
        send_message(user_text)
        st.rerun()
