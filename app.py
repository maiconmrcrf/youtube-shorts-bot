"""
app.py — Chat de IA (Groq + Mistral + OpenRouter)
Sem Gemini. Sem YouTube. Só conversa.
"""
import json
import os
import urllib.request
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

GROQ_KEY       = os.environ.get("GROQ_API_KEY", "").strip()
MISTRAL_KEY    = os.environ.get("MISTRAL_API_KEY", "").strip()
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

HISTORICO = []  # histórico da conversa (em memória)


def chamar_ia(mensagem):
    """Cascata: Groq -> Mistral -> OpenRouter."""
    tentativas = [
        ("Groq",       "https://api.groq.com/openai/v1/chat/completions",  GROQ_KEY,       "openai/gpt-oss-120b"),
        ("Mistral",    "https://api.mistral.ai/v1/chat/completions",       MISTRAL_KEY,    "mistral-small-latest"),
        ("OpenRouter", "https://openrouter.ai/api/v1/chat/completions",    OPENROUTER_KEY, "nvidia/nemotron-3.5-lightning:free"),
    ]

    # Monta histórico (últimas 10 mensagens)
    msgs = [{"role": "system", "content": "Voce e uma IA pessoal amigavel. Responda em portugues BR de forma direta e util."}]
    for h in HISTORICO[-10:]:
        msgs.append({"role": "user", "content": h["user"]})
        msgs.append({"role": "assistant", "content": h["ia"]})
    msgs.append({"role": "user", "content": mensagem})

    for nome, url, key, model in tentativas:
        if not key:
            continue
        try:
            body = {"model": model, "messages": msgs, "temperature": 0.7}
            req = urllib.request.Request(
                url, data=json.dumps(body).encode(),
                headers={
                    "Authorization": "Bearer " + key,
                    "Content-Type": "application/json",
                    "User-Agent": UA,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode())
            resp = d["choices"][0]["message"]["content"]
            return resp, nome
        except Exception:
            continue

    return None, "Nenhuma IA respondeu"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    msg = request.form.get("msg", "").strip()
    if not msg:
        return jsonify({"erro": "Mensagem vazia"}), 400

    resp, quem = chamar_ia(msg)

    if resp:
        HISTORICO.append({"user": msg, "ia": resp})
        return jsonify({"ok": True, "resposta": resp, "ia": quem})
    else:
        return jsonify({"erro": "Nenhuma IA respondeu. Verifique as chaves."}), 500


@app.route("/limpar", methods=["POST"])
def limpar():
    HISTORICO.clear()
    return jsonify({"ok": True})


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
