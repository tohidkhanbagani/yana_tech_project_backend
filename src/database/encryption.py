import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Load env variables from root .env
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
load_dotenv(dotenv_path=env_path)

_FERNET_INSTANCE = None

def get_fernet_instance():
    global _FERNET_INSTANCE
    if _FERNET_INSTANCE is not None:
        return _FERNET_INSTANCE
    
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        # Generate new key
        key = Fernet.generate_key().decode('utf-8')
        os.environ["ENCRYPTION_KEY"] = key
        # Append to .env file
        try:
            if os.path.exists(env_path):
                # Ensure a new line at the end
                with open(env_path, "r") as f:
                    content = f.read()
                newline = "" if content.endswith("\n") else "\n"
                with open(env_path, "a") as f:
                    f.write(f"{newline}ENCRYPTION_KEY={key}\n")
            else:
                with open(env_path, "w") as f:
                    f.write(f"ENCRYPTION_KEY={key}\n")
        except Exception as e:
            # Fallback if file write fails (e.g. read-only env)
            pass
                
    _FERNET_INSTANCE = Fernet(key.encode('utf-8'))
    return _FERNET_INSTANCE

def encrypt_data(plain_text: str) -> str:
    if not plain_text:
        return plain_text
    try:
        fernet = get_fernet_instance()
        return fernet.encrypt(str(plain_text).encode('utf-8')).decode('utf-8')
    except Exception:
        return plain_text

def decrypt_data(cipher_text: str) -> str:
    if not cipher_text:
        return cipher_text
    try:
        fernet = get_fernet_instance()
        return fernet.decrypt(str(cipher_text).encode('utf-8')).decode('utf-8')
    except Exception:
        # Decryption fallback: if not encrypted or decryption fails, return as-is
        return cipher_text
