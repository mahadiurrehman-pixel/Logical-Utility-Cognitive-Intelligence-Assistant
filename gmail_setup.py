#!/usr/bin/env python3
"""
LUCIA Gmail Setup — OAuth Re-Authentication
Automatically detects old tokens and requests new scopes.
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

TOKEN_FILE = Path(__file__).resolve().parent / "token.json"
REQUIRED_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Check if existing token has correct scopes
needs_reauth = False
if TOKEN_FILE.exists():
    try:
        with open(TOKEN_FILE, "r") as f:
            token_data = json.load(f)
        token_scopes = set(token_data.get("scopes", []))
        if not set(REQUIRED_SCOPES).issubset(token_scopes):
            print("🔄 Purane token mein send permission nahi hai.")
            print(f"   Purane scopes: {token_scopes}")
            print(f"   Naye scopes:   {set(REQUIRED_SCOPES)}")
            needs_reauth = True
    except Exception:
        needs_reauth = True

if needs_reauth and TOKEN_FILE.exists():
    print("🗑️  Purana token delete ho raha hai (naye scopes ke liye)...")
    os.remove(TOKEN_FILE)

from tools.gmail_tools import authenticate_gmail

print("=" * 55)
print("📧 LUCIA GMAIL SETUP (Read + Send + Draft)")
print("=" * 55)
print()
print("Browser khulega → Google login → 'Allow' karein.")
print("⚠️  Ab send permission bhi maangi jayegi.")
print()
input("Ready? Press Enter...")

result = authenticate_gmail()

if result["success"]:
    print(f"\n✅ {result['message']}")
    print("\nCommands:")
    print("  📥 'Mere unread emails padho'")
    print("  📤 'Ali ko email bhejo ke kal meeting hai'")
    print("  📝 'Draft banao sara@gmail.com ke liye'")
    print("  🔍 'Gmail mein invoice search karo'")
else:
    print(f"\n❌ {result['message']}")