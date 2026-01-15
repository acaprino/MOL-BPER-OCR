import os
import io
import json
import re
import time
import base64
from typing import Dict, Any, Optional, Tuple, List

import pandas as pd
from PIL import Image, ImageEnhance, ImageFilter

from openai import OpenAI

# -----------------------------
# CONFIG
# -----------------------------
SCREENSHOTS = [
    "mnt/data/screen 1.png",
    "mnt/data/screen 2.png",
    "mnt/data/screen 3.png",
    "mnt/data/screen 4.png",
]
GROUND_TRUTH_CSV = "mnt/data/dati.csv"

# Pricing (USD per 1M tokens) - aggiornabile da config
PRICING_PER_1M = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

# Crop percentuali (robusti a PC diversi)
CROPS = {
    "FULL": None,
    # Tipico: taglia topbar browser e sidebar sinistra
    "CONTENT": (0.18, 0.12, 0.98, 0.98),
    # Porzione bassa per "Situazione familiare" e "Note"
    "LOWER": (0.18, 0.45, 0.98, 0.98),
}

# Campi target (coerenti con la vostra ground truth)
FIELD_KEYS = [
    "ndg",
    "denominazione",
    "tipo",
    "evidenze",
    "filiale_relazione",
    "ultima_validazione_scheda_privati",
    "professione_principale",
    "numero_mensilita",
    "retribuzione_annua_netta",
    "tipo_contratto",
    "datore_lavoro_anagrafica",
    "dal",
    "rating_ufficiale",
    "score_cgs",
    "nr_altri_componenti_nucleo_familiare",
    "di_cui_percepiscono_reddito",
    "importo_totale_annuo_altri_componenti",
    "note_scheda_privati",
]

PROMPT = """
Sei un sistema di estrazione dati da screenshot di una web app (UI banca).
Devi estrarre SOLO i campi richiesti e restituire JSON conforme allo schema.

Regole:
- Se un valore non è presente o non è leggibile: value = null e confidence <= 0.3.
- Trattare "N/D", "ND", "---", vuoto come null.
- Non inventare mai valori.
- Per ogni campo: includi evidence_text (breve estratto) e section (titolo sezione se visibile).
- Se ci sono più soggetti (NDG 1..4, Denominazione 1..4, Ruolo 1..4), popola l'array soggetti.

Campi (label/sinonimi):
- ndg: "NDG"
- denominazione: "DENOMINAZIONE", "Nominativo"
- tipo: "Tipo"
- evidenze: "Evidenze"
- filiale_relazione: "Filiale relazione"
- ultima_validazione_scheda_privati: "Ultima validazione"
- professione_principale: "PROFESSIONE PRINCIPALE"
- numero_mensilita: "NUMERO MENSILITÀ", "MENSILITA"
- retribuzione_annua_netta: "RETRIBUZIONE ANNUA NETTA"
- tipo_contratto: "TIPO CONTRATTO"
- datore_lavoro_anagrafica: "DATORE DI LAVORO", "ANAGRAFICA"
- dal: "DAL"
- rating_ufficiale: "RATING UFFICIALE"
- score_cgs: "SCORE CGS"
- nr_altri_componenti_nucleo_familiare: "NR. ALTRI COMPONENTI NUCLEO FAMILIARE"
- di_cui_percepiscono_reddito: "DI CUI PERCEPISCONO REDDITO"
- importo_totale_annuo_altri_componenti: "IMPORTO TOTALE ANNUO"
- note_scheda_privati: "NOTE", "NOTE CONCLUSIVE"

Restituisci SOLO JSON.
""".strip()

# -----------------------------
# Structured Outputs JSON Schema (strict)
# -----------------------------
RESPONSE_SCHEMA = {
    "name": "bper_screen_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "screen_id": {"type": "string"},
            "attempt": {"type": "string"},
            "fields": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    k: {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "properties": {
                            "value": {"type": ["string", "number", "integer", "null"]},
                            "confidence": {"type": "number"},
                            "evidence_text": {"type": ["string", "null"]},
                            "section": {"type": ["string", "null"]},
                        },
                        "required": ["value", "confidence", "evidence_text", "section"],
                    }
                    for k in FIELD_KEYS
                },
                "required": FIELD_KEYS,
            },
            "soggetti": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "ndg": {"type": ["string", "null"]},
                        "denominazione": {"type": ["string", "null"]},
                        "ruolo": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                        "evidence_text": {"type": ["string", "null"]},
                    },
                    "required": ["ndg", "denominazione", "ruolo", "confidence", "evidence_text"],
                },
            },
        },
        "required": ["screen_id", "attempt", "fields", "soggetti"],
    },
}

# -----------------------------
# Helpers
# -----------------------------
def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = PRICING_PER_1M.get(model)
    if not p:
        return 0.0
    return (prompt_tokens / 1_000_000) * p["input"] + (completion_tokens / 1_000_000) * p["output"]

def normalize_image(img: Image.Image, long_side: int = 1800) -> Image.Image:
    w, h = img.size
    scale = long_side / max(w, h)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))
    img = ImageEnhance.Contrast(img).enhance(1.05)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))
    return img

def crop_relative(img: Image.Image, box: Tuple[float, float, float, float]) -> Image.Image:
    w, h = img.size
    l = int(box[0] * w)
    t = int(box[1] * h)
    r = int(box[2] * w)
    b = int(box[3] * h)
    return img.crop((l, t, r, b))

def img_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def is_nullish(v: Any) -> bool:
    if v is None:
        return True
    s = str(v).strip().lower()
    return s in ("", "n/d", "nd", "---", "null", "none", "nan")

def pick_best(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    if not a:
        return b
    if not b:
        return a
    av, bv = a.get("value"), b.get("value")
    an, bn = is_nullish(av), is_nullish(bv)
    if an and not bn:
        return b
    if bn and not an:
        return a
    return a if a.get("confidence", 0.0) >= b.get("confidence", 0.0) else b

def merge_attempts(attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged = attempts[0]
    for a in attempts[1:]:
        for k in FIELD_KEYS:
            merged["fields"][k] = pick_best(merged["fields"][k], a["fields"][k])
        # soggetti: dedup semplice per (ndg, denominazione, ruolo)
        seen = set((s.get("ndg"), s.get("denominazione"), s.get("ruolo")) for s in merged.get("soggetti", []))
        for s in a.get("soggetti", []):
            key = (s.get("ndg"), s.get("denominazione"), s.get("ruolo"))
            if key not in seen:
                merged["soggetti"].append(s)
                seen.add(key)
    merged["attempt"] = "MERGED"
    return merged

def norm_text(x: Any) -> str:
    s = "" if x is None else str(x)
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower()

def norm_number_str(x: Any) -> str:
    """Normalizza 27.000 / 27000 / 27,000 -> 27000 (stringa)"""
    if x is None:
        return ""
    s = str(x).strip()
    s = s.replace(".", "").replace(",", "")
    return s

def classify_field(gt_val, pred_val) -> str:
    gt_null = is_nullish(gt_val) or (str(gt_val).strip().lower() == "nan")
    pr_null = is_nullish(pred_val)

    if not gt_null and pr_null:
        return "MISSING"
    if gt_null and not pr_null:
        return "HALLUCINATED"
    if gt_null and pr_null:
        return "OK_NULL"
    # entrambi presenti
    return "OK" if norm_text(pred_val) == norm_text(gt_val) else "WRONG"

def dataset_mismatch_guard(screen_id: str, gt_kv: Dict[str, Any], pred: Dict[str, Any]) -> bool:
    # usa NDG e DENOMINAZIONE se presenti in GT per quel screen
    gt_ndg = gt_kv.get("NDG") or gt_kv.get("NDG 1")
    gt_den = gt_kv.get("DENOMINAZIONE") or gt_kv.get("DENOMINAZIONE 1")

    pr_ndg = (pred.get("fields", {}).get("ndg") or {}).get("value")
    pr_den = (pred.get("fields", {}).get("denominazione") or {}).get("value")

    # se GT ha una delle ancore, e pred non combacia, segnala mismatch
    if gt_ndg and pr_ndg and norm_number_str(gt_ndg) != norm_number_str(pr_ndg):
        return True
    if gt_den and pr_den and norm_text(gt_den) != norm_text(pr_den):
        return True
    return False

def build_debug_report(outputs: Dict[str, Dict[str, Any]], gt: Dict[str, Dict[str, Any]], out_csv_path: str):
    rows = []
    for scr, gt_kv in gt.items():
        pred = outputs.get(scr)
        if not pred:
            continue

        mismatch = dataset_mismatch_guard(scr, gt_kv, pred)

        for gt_key, gt_val in gt_kv.items():
            # normalizza key per match mapping
            gt_key_norm = str(gt_key).strip()
            schema_key = CSV_TO_SCHEMA.get(gt_key_norm)
            if not schema_key:
                continue

            field = (pred.get("fields", {}) or {}).get(schema_key) or {}
            pred_val = field.get("value")
            conf = field.get("confidence")
            evidence = field.get("evidence_text")
            section = field.get("section")

            status = "DATASET_MISMATCH" if mismatch else classify_field(gt_val, pred_val)

            meta = pred.get("_meta", {})
            rows.append({
                "screen": scr,
                "field": schema_key,
                "gt_key": gt_key_norm,
                "gt_value": gt_val,
                "pred_value": pred_val,
                "confidence": conf,
                "evidence_text": evidence,
                "section": section,
                "status": status,
                "model": meta.get("model"),
                "attempt": meta.get("attempt"),
                "prompt_tokens": meta.get("prompt_tokens"),
                "completion_tokens": meta.get("completion_tokens"),
                "total_tokens": meta.get("total_tokens"),
                "estimated_cost_usd": meta.get("estimated_cost_usd"),
                "latency_ms": meta.get("latency_ms"),
            })

    pd.DataFrame(rows).to_csv(out_csv_path, index=False, encoding="utf-8")

# -----------------------------
# VLM call (Responses API + Structured Outputs)
# -----------------------------
def call_vlm(client: OpenAI, image_bytes: bytes, prompt: str, screen_id: str, attempt: str, model: str="gpt-4o") -> Dict[str, Any]:
    import base64, time
    base64_image = base64.b64encode(image_bytes).decode('utf-8')

    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Estrai i campi richiesti dallo screenshot."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                ],
            }
        ],
        response_format={"type": "json_schema", "json_schema": RESPONSE_SCHEMA},
    )
    dt_ms = int((time.time() - t0) * 1000)

    out = json.loads(resp.choices[0].message.content)

    usage = getattr(resp, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
    total_tokens = getattr(usage, "total_tokens", 0) if usage else 0
    cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)

    out["_meta"] = {
        "model": model,
        "screen_id": screen_id,
        "attempt": attempt,
        "latency_ms": dt_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": cost_usd,
    }
    out["screen_id"] = screen_id
    out["attempt"] = attempt
    return out

# -----------------------------
# Orchestrator per singolo screenshot
# -----------------------------
def extract_from_screen(client: OpenAI, path: str) -> Dict[str, Any]:
    img = Image.open(path).convert("RGB")
    img = normalize_image(img)

    screen_id = os.path.splitext(os.path.basename(path))[0]
    attempts = []

    for crop_name, rel_box in CROPS.items():
        work = img if rel_box is None else crop_relative(img, rel_box)
        payload = img_to_png_bytes(work)

        out = call_vlm(client, payload, PROMPT, screen_id=screen_id, attempt=crop_name)
        attempts.append(out)

        # Early stop: se 2 dei 3 campi "ancora" sono buoni
        good = 0
        for k in ("ndg", "denominazione", "retribuzione_annua_netta"):
            field_data = out["fields"].get(k)
            if field_data is None:
                continue
            v = field_data["value"]
            c = field_data["confidence"]
            if (not is_nullish(v)) and c >= 0.75:
                good += 1
        if good >= 2:
            break

    return merge_attempts(attempts)

# -----------------------------
# Evaluation vs dati.csv
# -----------------------------
def load_ground_truth(csv_path: str) -> Dict[str, Dict[str, Any]]:
    df = pd.read_csv(csv_path)

    df["Screenshot"] = df["Screenshot"].astype(str).str.strip()
    df["Denominazione da attribuire"] = df["Denominazione da attribuire"].astype(str).str.strip()

    # colonna "Valore rilevato " ha spazio finale nel file
    val_col = "Valore rilevato "
    df[val_col] = df[val_col].astype(str).str.strip()

    gt: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        scr = row["Screenshot"]
        key = row["Denominazione da attribuire"]
        if key is None or str(key).strip().lower() in ("nan", ""):
            continue
        key = str(key).strip()   # IMPORTANT: elimina trailing spaces tipo "Evidenze "
        val = row[val_col]
        gt.setdefault(scr, {})[key] = val
    return gt

# Mapping minimo CSV -> schema (puoi estenderlo)
CSV_TO_SCHEMA = {
    "NDG": "ndg",
    "DENOMINAZIONE": "denominazione",
    "Tipo": "tipo",
    "Evidenze": "evidenze",
    "Filiale relazione": "filiale_relazione",
    "Ultima validazione scheda privati": "ultima_validazione_scheda_privati",
    "Professione principale": "professione_principale",
    "Numero mensilità": "numero_mensilita",
    "Retribuzione annua netta": "retribuzione_annua_netta",
    "Tipo contratto": "tipo_contratto",
    "DATORE DI LAVORO ANAGRAFICA": "datore_lavoro_anagrafica",
    "DAL": "dal",
    "RATING UFFICIALE": "rating_ufficiale",
    "SCORE CGS": "score_cgs",
    "Nr altri componenti nucleo familiare": "nr_altri_componenti_nucleo_familiare",
    "Di cui percepiscono reddito": "di_cui_percepiscono_reddito",
    "Importo totale annuo altri componenti nucleo familiare": "importo_totale_annuo_altri_componenti",
    "Note Scheda Privati": "note_scheda_privati",
}

def eval_outputs(outputs: Dict[str, Dict[str, Any]], gt: Dict[str, Dict[str, Any]]) -> None:
    total = 0
    correct = 0
    per_field = {}

    for scr, kv in gt.items():
        # scr es: "screen 1" -> schema id: "screen 1" senza estensione
        pred = outputs.get(scr, {})
        if not pred:
            continue

        for csv_key, gt_val in kv.items():
            if csv_key not in CSV_TO_SCHEMA:
                continue
            schema_key = CSV_TO_SCHEMA[csv_key]
            
            field_data = pred.get("fields", {}).get(schema_key)
            pred_val = field_data["value"] if field_data else None

            # Normalizzazione numeri per importi
            if schema_key in ("retribuzione_annua_netta", "importo_totale_annuo_altri_componenti"):
                ok = norm_number_str(pred_val) == norm_number_str(gt_val)
            else:
                ok = norm_text(pred_val) == norm_text(gt_val)

            total += 1
            correct += int(ok)
            per_field.setdefault(schema_key, [0, 0])
            per_field[schema_key][0] += int(ok)
            per_field[schema_key][1] += 1

    acc = (correct / total) if total else 0.0
    print(f"\nOVERALL: {correct}/{total} = {acc:.2%}\n")
    for k, (c, t) in sorted(per_field.items(), key=lambda x: x[0]):
        print(f"{k:40s} {c:3d}/{t:3d} = {(c/t):.2%}")

# -----------------------------
# -----------------------------
def main():
    client = OpenAI()  # legge OPENAI_API_KEY da env

    gt = load_ground_truth(GROUND_TRUTH_CSV)

    outputs: Dict[str, Dict[str, Any]] = {}
    for p in SCREENSHOTS:
        if not os.path.exists(p):
            print(f"Warning: File not found {p}")
            continue
        screen_id = os.path.splitext(os.path.basename(p))[0]  # "screen 1"
        print(f"Extracting {screen_id} ...")
        outputs[screen_id] = extract_from_screen(client, p)

    # Salva output per ispezione
    output_path = "mnt/data/poc_outputs.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(outputs, f, ensure_ascii=False, indent=2)

    # Valuta
    eval_outputs(outputs, gt)
    build_debug_report(outputs, gt, "mnt/data/poc_debug.csv")

    print(f"\nSaved: {output_path}")

if __name__ == "__main__":
    main()
