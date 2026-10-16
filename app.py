"""
app.py — Chat ÚNICO com 2 IAs (Gemini e Groq).
Trocar de aba NÃO perde a conversa. A nova IA lê o histórico.
"""
import json
import os
import urllib.request
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

GEMINI_KEY = os.environ.get("GEMINI_KEY_IA", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_KEY   = os.environ.get("GROQ_API_KEY", "").strip()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

# Histórico ÚNICO (compartilhado entre as IAs)
HISTORICO = []
IA_ATIVA = "gemini"  # gemini ou groq


# ============================================================
# GEMINI
# ============================================================
def chamar_gemini(mensagem):
    if not GEMINI_KEY:
        return None, "sem chave"

    contents = []
    # Manda as últimas 15 interações pra dar contexto
    for h in HISTORICO[-15:]:
        quem = h.get("ia", "Gemini")
        contents.append({"role": "user", "parts": [{"text": h["user"]}]})
        contents.append({"role": "model", "parts": [{"text": f"[{quem}] {h['ia']}"}]})
    contents.append({"role": "user", "parts": [{"text": mensagem}]})

    # Instrução do sistema: avisa que pode ter resposta de outra IA
    sys_instruction = (
        "Você é uma IA pessoal amigável chamada Gemini. Responda em português BR.\n"
        "IMPORTANTE: no histórico abaixo, mensagens marcadas com [Groq] foram "
        "dadas por OUTRA IA (não por você). Use essas mensagens como contexto "
        "pra entender o assunto da conversa, mas responda com sua própria opinião."
    )

    modelos = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
    for modelo in modelos:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={GEMINI_KEY}"
            body = {
                "contents": contents,
                "systemInstruction": {"parts": [{"text": sys_instruction}]},
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
        except Exception:
            continue
    return None, "Gemini falhou"


# ============================================================
# GROQ
# ============================================================
def chamar_groq(mensagem):
    if not GROQ_KEY:
        return None, "sem chave"

    sys_instruction = (
        "Você é uma IA pessoal amigável chamada Groq. Responda em português BR.\n"
        "IMPORTANTE: no histórico abaixo, mensagens marcadas com [Gemini] foram "
        "dadas por OUTRA IA (não por você). Use essas mensagens como contexto "
        "pra entender o assunto da conversa, mas responda com sua própria opinião."
    )

    msgs = [{"role": "system", "content": sys_instruction}]
    # Manda as últimas 15 interações com a marcação da IA que respondeu
    for h in HISTORICO[-15:]:
        quem = h.get("ia", "Groq")
        msgs.append({"role": "user", "content": h["user"]})
        msgs.append({"role": "assistant", "content": f"[{quem}] {h['ia']}"})
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
        return jsonify({"erro": f"Nenhuma resposta de {ia}. Verifique a chave."}), 500


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
