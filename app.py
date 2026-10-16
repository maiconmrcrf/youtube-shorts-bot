"""
app.py — Chat com 2 IAs (Gemini e Groq). Historico compartilhado.
"""
import json
import os
import urllib.request
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

GEMINI_KEY = os.environ.get("GEMINI_KEY_IA", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_KEY   = os.environ.get("GROQ_API_KEY", "").strip()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

HISTORICO = []
IA_ATIVA = "gemini"


def chamar_gemini(mensagem):
    if not GEMINI_KEY:
        return None, "sem chave"

    contents = []
    for h in HISTORICO[-15:]:
        quem = h.get("quem", "IA")
        contents.append({"role": "user", "parts": [{"text": h["user"]}]})
        contents.append({"role": "model", "parts": [{"text": "[" + quem + "]: " + h["ia"]}]})
    contents.append({"role": "user", "parts": [{"text": mensagem}]})

    instrucao = "Voce e uma IA pessoal amigavel chamada Gemini. Responda em portugues BR. IMPORTANTE: mensagens marcadas com [Groq] foram dadas por OUTRA IA. Voce PODE e DEVE corrigir o Groq se ele errar. Sempre que o usuario perguntar se algo esta certo, olhe a ultima resposta do Groq e avalie com sinceridade."

    modelos = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
    for modelo in modelos:
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/" + modelo + ":generateContent?key=" + GEMINI_KEY
            body = {"contents": contents, "systemInstruction": {"parts": [{"text": instrucao}]}}
            req = urllib.request.Request(
                url, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode())
            return d["candidates"][0]["content"]["parts"][0]["text"], "Gemini"
        except Exception:
            continue
    return None, "Gemini falhou"


def chamar_groq(mensagem):
    if not GROQ_KEY:
        return None, "sem chave"

    instrucao = "Voce e uma IA pessoal amigavel chamada Groq. Responda em portugues BR. IMPORTANTE: mensagens marcadas com [Gemini] foram dadas por OUTRA IA. Voce PODE e DEVE corrigir o Gemini se ele errar. Sempre que o usuario perguntar se algo esta certo, olhe a ultima resposta do Gemini e avalie com sinceridade."

    msgs = [{"role": "system", "content": instrucao}]
    for h in HISTORICO[-15:]:
        quem = h.get("quem", "IA")
        msgs.append({"role": "user", "content": h["user"]})
        msgs.append({"role": "assistant", "content": "[" + quem + "]: " + h["ia"]})
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
        return d["choices"][0]["message"]["content"], "Groq"
    except Exception:
        return None, "Groq falhou"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    global IA_ATIVA
    msg = request.form.get("msg", "").strip()
    ia = request.form.get("ia", IA_ATIVA).strip().lower()

    if not msg:
        return jsonify({"erro": "Mensagem vazia"}), 400

    IA_ATIVA = ia

    if ia == "groq":
        resp, quem = chamar_groq(msg)
    else:
        ia = "gemini"
        resp, quem = chamar_gemini(msg)

    if resp:
        HISTORICO.append({"user": msg, "ia": resp, "quem": quem})
        return jsonify({"ok": True, "resposta": resp, "ia": quem})
    else:
        return jsonify({"erro": "Nenhuma resposta de " + ia}), 500


@app.route("/historico")
def historico():
    return jsonify(HISTORICO)


@app.route("/limpar", methods=["POST"])
def limpar():
    HISTORICO.clear()
    return jsonify({"ok": True})


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
