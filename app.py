"""
app.py — Chat com 2 IAs (Gemini e Groq) + geração de vídeo (3 APIs).
"""
import base64
import json
import os
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)

GEMINI_KEY     = os.environ.get("GEMINI_KEY_IA", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_KEY       = os.environ.get("GROQ_API_KEY", "").strip()
CF_ACCOUNT     = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
CF_TOKEN       = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
HF_TOKEN       = os.environ.get("HUGGINGFACE_TOKEN", "").strip()
MH_KEY         = os.environ.get("MAGIC_HOUR_API_KEY", "").strip()
REPLICATE_KEY  = os.environ.get("REPLICATE_API_TOKEN", "").strip()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

HISTORICO = []
IA_ATIVA = "gemini"

MIDIA = Path("/tmp/midia_ia")
MIDIA.mkdir(parents=True, exist_ok=True)


def detectar_pedido(msg):
    m = msg.lower().strip()

    for g in ["cria uma imagem", "crie uma imagem", "gera uma imagem", "gere uma imagem",
              "cria imagem", "gera imagem", "faz uma imagem", "desenha", "cria um desenho"]:
        if g in m:
            idx = m.find(g)
            return "imagem", msg[idx + len(g):].strip(" de: sobre")

    for g in ["cria um video", "crie um video", "gera um video", "gere um video",
              "faz um video", "cria video", "gera video"]:
        if g in m:
            idx = m.find(g)
            return "video", msg[idx + len(g):].strip(" de: sobre")

    return None, None


# ============================================================
# IMAGEM (Cloudflare FLUX)
# ============================================================
def gerar_imagem(prompt):
    if not CF_ACCOUNT or not CF_TOKEN:
        return None, "Cloudflare nao configurado"

    url = "https://api.cloudflare.com/client/v4/accounts/" + CF_ACCOUNT + "/ai/run/@cf/black-forest-labs/flux-1-schnell"
    body = json.dumps({"prompt": prompt, "steps": 4}).encode()

    req = urllib.request.Request(url, data=body,
        headers={"Authorization": "Bearer " + CF_TOKEN, "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
        if not d.get("success"):
            return None, "FLUX falhou"
        img_bytes = base64.b64decode(d["result"]["image"])
        nome = "img_" + uuid.uuid4().hex[:8] + ".jpg"
        (MIDIA / nome).write_bytes(img_bytes)
        return nome, None
    except Exception as e:
        return None, str(e)


# ============================================================
# VIDEO — 3 APIs em cascata
# ============================================================
def gerar_video_magichour(prompt, duracao=5):
    """Magic Hour - 400 creditos gratis."""
    if not MH_KEY:
        return None, "sem chave"

    url = "https://api.magichour.ai/v1/text-to-video"
    body = json.dumps({
        "end_seconds": duracao,
        "aspect_ratio": "9:16",
        "resolution": "480p",
        "model": "ltx-2.5",
        "style": {"prompt": prompt}
    }).encode()

    try:
        req = urllib.request.Request(url, data=body,
            headers={"Authorization": "Bearer " + MH_KEY, "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())

        job_id = d.get("id")
        if not job_id:
            return None, "sem job id"

        # Aguarda processar (max 3 min)
        for i in range(36):
            time.sleep(5)
            url_status = "https://api.magichour.ai/v1/video-projects/" + job_id
            req2 = urllib.request.Request(url_status,
                headers={"Authorization": "Bearer " + MH_KEY}, method="GET")
            with urllib.request.urlopen(req2, timeout=30) as r2:
                s = json.loads(r2.read().decode())

            if s.get("status") == "complete":
                video_url = s.get("download", {}).get("url")
                if video_url:
                    nome = "vid_" + uuid.uuid4().hex[:8] + ".mp4"
                    urllib.request.urlretrieve(video_url, MIDIA / nome)
                    return nome, None
                return None, "sem URL"
            elif s.get("status") in ("error", "failed"):
                return None, "falhou"

        return None, "timeout"
    except Exception as e:
        return None, str(e)[:80]


def gerar_video_huggingface(prompt, duracao=5):
    """Hugging Face - gratis com fila."""
    if not HF_TOKEN:
        return None, "sem chave"

    # Usa o Space do AnimateDiff ou similar
    # (implementacao simplificada - so tenta)
    return None, "nao implementado"


def gerar_video_replicate(prompt, duracao=5):
    """Replicate - pago por uso."""
    if not REPLICATE_KEY:
        return None, "sem chave"

    url = "https://api.replicate.com/v1/predictions"
    body = json.dumps({
        "version": "9f747673945c62801b13b84701c783929c0ee784e4748ec062204894dda1a351",
        "input": {"prompt": prompt}
    }).encode()

    try:
        req = urllib.request.Request(url, data=body,
            headers={"Authorization": "Token " + REPLICATE_KEY, "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())

        pred_id = d.get("id")
        if not pred_id:
            return None, "sem id"

        for i in range(36):
            time.sleep(5)
            url_status = "https://api.replicate.com/v1/predictions/" + pred_id
            req2 = urllib.request.Request(url_status,
                headers={"Authorization": "Token " + REPLICATE_KEY}, method="GET")
            with urllib.request.urlopen(req2, timeout=30) as r2:
                s = json.loads(r2.read().decode())

            if s.get("status") == "succeeded":
                output = s.get("output")
                video_url = output if isinstance(output, str) else (output[0] if output else None)
                if video_url:
                    nome = "vid_" + uuid.uuid4().hex[:8] + ".mp4"
                    urllib.request.urlretrieve(video_url, MIDIA / nome)
                    return nome, None
                return None, "sem URL"
            elif s.get("status") == "failed":
                return None, "falhou"

        return None, "timeout"
    except Exception as e:
        return None, str(e)[:80]


def gerar_video(prompt, duracao=5):
    """Tenta Magic Hour -> Hugging Face -> Replicate."""
    tentativas = [
        ("Magic Hour", gerar_video_magichour),
        ("Hugging Face", gerar_video_huggingface),
        ("Replicate", gerar_video_replicate),
    ]
    for nome, func in tentativas:
        print(f"[video] tentando {nome}...")
        resultado, erro = func(prompt, duracao)
        if resultado:
            print(f"[video] {nome} OK")
            return resultado, None
        print(f"[video] {nome} falhou: {erro}")
    return None, "Todas as APIs de video falharam"


# ============================================================
# GEMINI (cascata)
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

    modelos = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite",
               "gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-flash-latest"]
    for modelo in modelos:
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/" + modelo + ":generateContent?key=" + GEMINI_KEY
            body = {"contents": contents, "systemInstruction": {"parts": [{"text": instrucao}]}}
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode())
            return d["candidates"][0]["content"]["parts"][0]["text"], "Gemini"
        except Exception:
            continue
    return None, "Gemini falhou"


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
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + GROQ_KEY, "Content-Type": "application/json", "User-Agent": UA},
            method="POST")
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
    tipo, prompt = detectar_pedido(msg)

    if tipo == "imagem" and prompt:
        nome, err = gerar_imagem(prompt)
        resp = "Aqui esta a imagem:" if not err else "Erro: " + err
        item = {"user": msg, "ia": resp, "quem": "IA", "tipo": "imagem", "midia": nome if not err else None}
        HISTORICO.append(item)
        return jsonify({"ok": True, "resposta": resp, "ia": "IA", "tipo": "imagem", "midia": item["midia"]})

    if tipo == "video" and prompt:
        nome, err = gerar_video(prompt)
        resp = "Aqui esta o video:" if not err else "Erro: " + err
        item = {"user": msg, "ia": resp, "quem": "IA", "tipo": "video", "midia": nome if not err else None}
        HISTORICO.append(item)
        return jsonify({"ok": True, "resposta": resp, "ia": "IA", "tipo": "video", "midia": item["midia"]})

    if ia == "groq":
        resp, quem = chamar_groq(msg)
    else:
        ia = "gemini"
        resp, quem = chamar_gemini(msg)

    if resp:
        HISTORICO.append({"user": msg, "ia": resp, "quem": quem})
        return jsonify({"ok": True, "resposta": resp, "ia": quem})
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
