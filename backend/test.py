import os

print("--- Test 1: valeurs par défaut (sans variables d'env) ---")
os.environ.pop("IMAP_LOOKBACK_DAYS", None)
os.environ.pop("IMAP_RETRY_COOLDOWN_MINUTES", None)

import imap_checker
print(imap_checker.LOOKBACK_DAYS, imap_checker.RETRY_COOLDOWN_MINUTES)

if imap_checker.LOOKBACK_DAYS == 30 and imap_checker.RETRY_COOLDOWN_MINUTES == 10:
    print("✅ PASS: valeurs par défaut correctes (30, 10)")
else:
    print(f"❌ FAIL: attendu (30, 10), obtenu ({imap_checker.LOOKBACK_DAYS}, {imap_checker.RETRY_COOLDOWN_MINUTES})")

print("\n--- Test 2: override via variables d'env ---")
os.environ["IMAP_LOOKBACK_DAYS"] = "7"
os.environ["IMAP_RETRY_COOLDOWN_MINUTES"] = "3"

import importlib
importlib.reload(imap_checker)
print(imap_checker.LOOKBACK_DAYS, imap_checker.RETRY_COOLDOWN_MINUTES)

if imap_checker.LOOKBACK_DAYS == 7 and imap_checker.RETRY_COOLDOWN_MINUTES == 3:
    print("✅ PASS: override via env correct (7, 3)")
else:
    print(f"❌ FAIL: attendu (7, 3), obtenu ({imap_checker.LOOKBACK_DAYS}, {imap_checker.RETRY_COOLDOWN_MINUTES})")