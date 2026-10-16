"""
app.py — Chat com 2 IAs (Gemini e Groq). Historico compartilhado.
Detecta pedidos de imagem/video e gera.
"""
import base64
import json
import os
import subprocess
import urllib.request
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)

GEMINI_KEY = os.environ.get("GEMINI_KEY_IA", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_KEY   = os.environ.get("GROQ_API_KEY", "").strip()
CF_ACCOUNT = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
CF_TOKEN   = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

HISTORICO = []
IA_ATIVA = "gemini"

# Pasta pra salvar imagens/videos
MIDIA = Path("/tmp/midia_ia")
MIDIA.mkdir(parents=True, exist_ok=True)


# ============================================================
# DETECTA SE QUER IMAGEM OU VIDEO
# ============================================================
def detectar_pedido(msg):
    """Retorna ('imagem', prompt) ou ('video', prompt) ou (None, None)."""
    m = msg.lower().strip()

    gatilhos_img = ["cria uma imagem", "crie uma imagem", "gera uma imagem", "gere uma imagem",
                    "cria imagem", "gera imagem", "faz uma imagem", "desenha", "cria um desenho",
                    "gera uma foto", "cria uma foto"]
    for g in gatilhos_img:
        if g in m:
            idx = m.find(g)
            resto = msg[idx + len(g):].strip(" de: sobre")
            return "imagem", resto

    gatilhos_vid = ["cria um video", "crie um video", "gera um video", "gere um video",
                    "faz um video", "cria video", "gera video"]
    for g in gatilhos_vid:
        if g in m:
            idx = m.find(g)
            resto = msg[idx + len(g):].strip(" de: sobre")
            return "video", resto

    return None, None


# ============================================================
# GERA IMAGEM (Cloudflare FLUX)
# ============================================================
def gerar_imagem(prompt):
    if not CF_ACCOUNT or not CF_TOKEN:
        return None, "Cloudflare nao configurado"

    url = "https://api.cloudflare.com/client/v4/accounts/" + CF_ACCOUNT + "/ai/run/@cf/black-forest-labs/flux-1-schnell"
    body = json.dumps({"prompt": prompt, "steps": 4}).encode()

    req = urllib.request.Request(
        url, data=body,
        headers={"Authorization": "Bearer " + CF_TOKEN, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
        if not d.get("success"):
            return None, "FLUX falhou: " + str(d.get("errors"))
        img_bytes = base64.b64decode(d["result"]["image"])
        nome = "img_" + uuid.uuid4().hex[:8] + ".jpg"
        caminho = MIDIA / nome
        caminho.write_bytes(img_bytes)
        return nome, None
    except Exception as e:
        return None, str(e)


# ============================================================
# GERA VIDEO (imagem + Ken Burns)
# ============================================================
def gerar_video(prompt, duracao=5):
    nome_img, err = gerar_imagem(prompt)
    if err:
        return None, err

    img_path = MIDIA / nome_img
    nome_vid = "vid_" + uuid.uuid4().hex[:8] + ".mp4"
    caminho = MIDIA / nome_vid

    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
           "-t", str(duracao),
           "-vf", "zoompan=z='min(zoom+0.0015,1.5)':d=125:s=720x1280,format=yuv420p",
           "-c:v", "libx264", "-preset", "fast", "-crf", "23", str(caminho)]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return nome_vid, None
    except Exception as e:
        return None, str(e)


# ============================================================
# GEMINI (cascata de modelos)
# ============================================================
def chamar_gemini(mensagem):
    if not GEMINI_KEY:
        return None, "sem chave"

    contents = []
    for h in HISTORICO[-15:]:
        quem = h.get("quem", "IA")
        contents.append({"role": "user", "parts": [{"text": h["user"]}]})
        contents.append({"role": "model", "parts": [{"text": "[" + quem + "]: " + h["ia"]}]})
    contents.append({"role": "user", "parts": [{"text": mensagem}]})

    instrucao = "Voce e uma IA pessoal amigavel chamada Gemini. Responda em portugues BR. IMPORTANTE: mensagens marcadas com [Groq] foram dadas por OUTRA IA. Voce PODE e DEVE corrigir o Groq se ele errar."

    # Cascata de modelos
    modelos = [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
    ]
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

    instrucao = "Voce e uma IA pessoal amigavel chamada Groq. Responda em portugues BR. IMPORTANTE: mensagens marcadas com [Gemini] foram dadas por OUTRA IA. Voce PODE e DEVE corrigir o Gemini se ele errar."

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
            headers={"Authorization": "Bearer " + GROQ_KEY, "Content-Type": "application/json", "User-Agent": UA},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
        return d["choices"][0]["message"]["content"], "Groq"
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

    # Detecta se quer imagem/video
    tipo, prompt = detectar_pedido(msg)

    if tipo == "imagem" and prompt:
        nome, err = gerar_imagem(prompt)
        if err:
            resp = "Erro ao gerar imagem: " + err
        else:
            resp = "Aqui esta a imagem:"
        HISTORICO.append({"user": msg, "ia": resp, "quem": "IA", "tipo": "imagem", "midia": nome if not err else None})
        return jsonify({"ok": True, "resposta": resp, "ia": "IA", "tipo": "imagem", "midia": nome if not err else None})

    if tipo == "video" and prompt:
        nome, err = gerar_video(prompt)
        if err:
            resp = "Erro ao gerar video: " + err
        else:
            resp = "Aqui esta o video:"
        HISTORICO.append({"user": msg, "ia": resp, "quem": "IA", "tipo": "video", "midia": nome if not err else None})
        return jsonify({"ok": True, "resposta": resp, "ia": "IA", "tipo": "video", "midia": nome if not err else None})

    # Conversa normal
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


@app.route("/midia/<path:filename>")
def midia(filename):
    p = MIDIA / filename
    if p.exists():
        if p.suffix == ".mp4":
            return send_file(str(p), mimetype="video/mp4")
        return send_file(str(p))
    return jsonify({"erro": "Nao encontrado"}), 404


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
