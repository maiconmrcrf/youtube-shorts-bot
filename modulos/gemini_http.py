"""gemini_http.py — Comunicação com a API do Gemini (silencioso)"""
import json
import os
import urllib.request
import urllib.error

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODELOS = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]


def _chamar(prompt, api_key, modelo, imagens_b64=None):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
    parts = [{"text": prompt}]
    if imagens_b64:
        for img in imagens_b64:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": img}})
    body = {"contents": [{"parts": parts}]}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    try:
        return d["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return ""


def gerar(prompt, api_key, imagens_b64=None, silencioso=True):
    """Tenta vários modelos em cascata. Silencioso = não imprime nada."""
    tentados = 0
    ultimo_erro = "?"
    for m in MODELOS:
        tentados += 1
        try:
            r = _chamar(prompt, api_key, m, imagens_b64=imagens_b64)
            if r:
                return r
        except urllib.error.HTTPError as e:
            ultimo_erro = f"{m}: HTTP {e.code}"
            continue
        except Exception as e:
            ultimo_erro = f"{m}: {e}"
            continue
    raise RuntimeError(f"Nenhum dos {tentados} modelos funcionou. Último: {ultimo_erro}")


def extrair_json(texto):
    """Extrai JSON de uma resposta (mesmo com texto antes/depois)."""
    if not texto:
        return None
    try:
        return json.loads(texto)
    except Exception:
        pass
    ini = texto.find("{")
    fim = texto.rfind("}")
    if ini >= 0 and fim > ini:
        try:
            return json.loads(texto[ini:fim+1])
        except Exception:
            pass
    return None
