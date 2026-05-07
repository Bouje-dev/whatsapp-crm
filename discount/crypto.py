# crypto.py
from cryptography.fernet import Fernet
from django.conf import settings
import base64
import os

def generate_key():
    return Fernet.generate_key()

def get_crypto():
    # احفظ هذا المفتاح في settings.py بشكل آمن
    key = settings.KEY.encode()
    return Fernet(key)

def encrypt_token(token):
    crypto = get_crypto()
    return crypto.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token):
    crypto = get_crypto()
    return crypto.decrypt(encrypted_token.encode()).decode()

