"""Diagnostica step-by-step per errori INVALID_ARGUMENT su Gemini."""
import os, base64, sys
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("LLM_API_KEY", "")
MODEL   = os.getenv("LLM_MODEL", "gemini-3-flash-preview")

print(f"Model : {MODEL}")
print(f"Key   : {API_KEY[:8]}...{API_KEY[-4:]}\n")

# ── Step 1: import ──────────────────────────────────────────
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import HumanMessage
    from pydantic import BaseModel
    from typing import Optional
    print("[OK] imports")
except Exception as e:
    sys.exit(f"[FAIL] imports: {e}")

# ── Step 2: crea modello senza safety_settings ───────────────
try:
    llm_plain = ChatGoogleGenerativeAI(model=MODEL, google_api_key=API_KEY)
    print("[OK] create model (no safety_settings)")
except Exception as e:
    sys.exit(f"[FAIL] create model: {e}")

# ── Step 3: chiamata testo puro ──────────────────────────────
try:
    resp = llm_plain.invoke("Di' solo: OK")
    print(f"[OK] text call → {resp.content[:60]!r}")
except Exception as e:
    sys.exit(f"[FAIL] text call: {e}")

# ── Step 4: crea modello CON safety_settings (come in produzione) ─
try:
    llm_safe = ChatGoogleGenerativeAI(
        model=MODEL,
        google_api_key=API_KEY,
        safety_settings={
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        },
    )
    resp2 = llm_safe.invoke("Di' solo: OK")
    print(f"[OK] text call WITH safety_settings → {resp2.content[:60]!r}")
except Exception as e:
    print(f"[FAIL] text call WITH safety_settings: {e}")
    print("      → safety_settings causa INVALID_ARGUMENT su questo modello")

# ── Step 5: structured output semplice ──────────────────────
class _Simple(BaseModel):
    risposta: Optional[str] = None

try:
    structured = llm_plain.with_structured_output(_Simple, include_raw=True, method="json_mode")
    r = structured.invoke("Rispondi con JSON: {\"risposta\": \"OK\"}")
    print(f"[OK] structured output json_mode → {r['parsed']}")
except Exception as e:
    print(f"[FAIL] structured output json_mode: {e}")

# ── Step 6: vision (immagine 1×1 pixel) ─────────────────────
tiny_png = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
    b'\x00\x11\x00\x01\xba\x98d&\x00\x00\x00\x00IEND\xaeB`\x82'
)
b64 = base64.b64encode(tiny_png).decode()
try:
    r = llm_plain.invoke([HumanMessage(content=[
        {"type": "text", "text": "Descrivi questa immagine in una parola."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ])])
    print(f"[OK] vision call → {r.content[:60]!r}")
except Exception as e:
    print(f"[FAIL] vision call: {e}")

print("\nDiagnostica completata.")
