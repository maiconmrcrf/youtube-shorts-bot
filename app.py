"""
app.py — Chat com 2 IAs (Gemini e Groq). Cada uma tem histórico separado.
"""
import json
import os
import urllib.request
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Chaves
GEMINI_KEY = os.environ.get("GEMINI_KEY_IA", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_KEY   = os.environ.get("GROQ_API_KEY", "").strip()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

# Históricos separados
HISTORICOS = {
    "gemini": [],
    "groq": [],
}


# ============================================================
# GEMINI
# ============================================================
def chamar_gemini(mensagem):
    if not GEMINI_KEY:
        return None, "sem chave"

    # Monta histórico
    contents = []
    for h in HISTORICOS["gemini"][-10:]:
        contents.append({"role": "user", "parts": [{"text": h["user"]}]})
        contents.append({"role": "model", "parts": [{"text": h["ia"]}]})
    contents.append({"role": "user", "parts": [{"text": mensagem}]})

    # Modelos em cascata
    modelos = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
    for modelo in modelos:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={GEMINI_KEY}"
            body = {
                "contents": contents,
                "systemInstruction": {"parts": [{"text": "Voce e uma IA pessoal amigavel. Responda em portugues BR de forma direta e util."}]},
            }
            req = urllib.request.Request(
                url, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode())
            resp = d["candidates"][0]["content"]["parts"][0]["text"]
            return resp, "Gemini"
        except Exception as e:
            continue
    return None, "Gemini falhou"


# ============================================================
# GROQ
# ============================================================
def chamar_groq(mensagem):
    if not GROQ_KEY:
        return None, "sem chave"

    msgs = [{"role": "system", "content": "Voce e uma IA pessoal amigavel. Responda em portugues BR de forma direta e util."}]
    for h in HISTORICOS["groq"][-10:]:
        msgs.append({"role": "user", "content": h["user"]})
        msgs.append({"role": "assistant", "content": h["ia"]})
    msgs.append({"role": "user", "content": mensagem})

    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        body = {"model": "openai/gpt-oss-120b", "messages": msgs, "temperature": 0.7}
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + GROQ_KEY,
                "Content-Type": "application/json",
                "User-Agent": UA,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
        resp = d["choices"][0]["message"]["content"]
        return resp, "Groq"
    except Exception:
        return None, "Groq falhou"


# ============================================================
# ROTAS
# ============================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    msg = request.form.get("msg", "").strip()
    ia = request.form.get("ia", "gemini").strip().lower()

    if not msg:
        return jsonify({"erro": "Mensagem vazia"}), 400

    if ia == "groq":
        resp, quem = chamar_groq(msg)
    else:
        ia = "gemini"
        resp, quem = chamar_gemini(msg)

    if resp:
        HISTORICOS[ia].append({"user": msg, "ia": resp})
        return jsonify({"ok": True, "resposta": resp, "ia": quem})
    else:
        return jsonify({"erro": f"Nenhuma resposta de {ia}. Verifique a chave."}), 500


@app.route("/historico/<ia>")
def historico(ia):
    ia = ia.lower()
    if ia not in HISTORICOS:
        return jsonify({"erro": "IA invalida"}), 400
    return jsonify(HISTORICOS[ia])


@app.route("/limpar/<ia>", methods=["POST"])
def limpar(ia):
    ia = ia.lower()
    if ia in HISTORICOS:
        HISTORICOS[ia].clear()
    return jsonify({"ok": True})


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
