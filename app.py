"""
app.py — Chat com 2 IAs + geração de vídeo pelo GEMINI (omni).
"""
import base64
import json
import os
import re
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

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

HISTORICO = []
IA_ATIVA = "gemini"

MIDIA = Path(__file__).parent / "midia"
MIDIA.mkdir(parents=True, exist_ok=True)


# ============================================================
# IMAGEM (Gemini 3.1 flash image ou Cloudflare)
# ============================================================
def ferramenta_imagem(prompt):
    # Tenta Gemini image primeiro
    if GEMINI_KEY:
        modelos_img = ["gemini-3.1-flash-image", "gemini-3-pro-image", "gemini-2.5-flash-image"]
        for modelo in modelos_img:
            try:
                url = "https://generativelanguage.googleapis.com/v1beta/models/" + modelo + ":generateContent?key=" + GEMINI_KEY
                body = {"contents": [{"role": "user", "parts": [{"text": "Gere uma imagem: " + prompt}]}]}
                req = urllib.request.Request(url, data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=90) as r:
                    d = json.loads(r.read().decode())
                # Procura partes com inline_data (imagem)
                for p in d["candidates"][0]["content"]["parts"]:
                    if "inline_data" in p:
                        img_bytes = base64.b64decode(p["inline_data"]["data"])
                        nome = "img_" + uuid.uuid4().hex[:8] + ".jpg"
                        (MIDIA / nome).write_bytes(img_bytes)
                        return nome, None
            except Exception:
                continue

    # Fallback Cloudflare
    if CF_ACCOUNT and CF_TOKEN:
        url = "https://api.cloudflare.com/client/v4/accounts/" + CF_ACCOUNT + "/ai/run/@cf/black-forest-labs/flux-1-schnell"
        body = json.dumps({"prompt": prompt, "steps": 4}).encode()
        req = urllib.request.Request(url, data=body,
            headers={"Authorization": "Bearer " + CF_TOKEN, "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode())
            if d.get("success"):
                img_bytes = base64.b64decode(d["result"]["image"])
                nome = "img_" + uuid.uuid4().hex[:8] + ".jpg"
                (MIDIA / nome).write_bytes(img_bytes)
                return nome, None
        except Exception:
            pass

    return None, "Todas as APIs de imagem falharam"


# ============================================================
# VIDEO (Gemini omni - GRATIS e sem limite pratico)
# ============================================================
def ferramenta_video_gemini(prompt, duracao=5):
    """Gera video com o Gemini Omni."""
    if not GEMINI_KEY:
        return None, "sem chave"

    # Modelos de video do Gemini
    modelos = ["gemini-omni-1.1-flash", "gemini-omni-flash-preview"]

    for modelo in modelos:
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/" + modelo + ":generateContent?key=" + GEMINI_KEY
            body = {
                "contents": [{"role": "user", "parts": [{
                    "text": "Gere um video de " + str(duracao) + " segundos: " + prompt + ". Formato vertical 9:16."
                }]}],
                "generationConfig": {
                    "responseModalities": ["VIDEO"]
                }
            }
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read().decode())

            # Procura por video na resposta
            candidatos = d.get("candidates", [])
            if not candidatos:
                continue

            for p in candidatos[0].get("content", {}).get("parts", []):
                # Formato 1: inline_data com video
                if "inline_data" in p and "video" in p["inline_data"].get("mime_type", ""):
                    vid_bytes = base64.b64decode(p["inline_data"]["data"])
                    nome = "vid_gem_" + uuid.uuid4().hex[:8] + ".mp4"
                    (MIDIA / nome).write_bytes(vid_bytes)
                    return nome, None

                # Formato 2: file_data com URL
                if "file_data" in p:
                    url_vid = p["file_data"].get("file_uri") or p["file_data"].get("url")
                    if url_vid:
                        nome = "vid_gem_" + uuid.uuid4().hex[:8] + ".mp4"
                        urllib.request.urlretrieve(url_vid, MIDIA / nome)
                        return nome, None
        except Exception as e:
            print("[gemini video] " + modelo + " falhou: " + str(e)[:100])
            continue

    return None, "Gemini Omni nao retornou video"


# ============================================================
# GERAR VIDEO
# ============================================================
def gerar_video(prompt, duracao=5):
    print("[video] tentando Gemini Omni...")
    res, err = ferramenta_video_gemini(prompt, duracao)
    if res:
        return res, None, "Gemini Omni"
    return None, "Gemini Omni falhou: " + str(err), None


# ============================================================
# IA (texto)
# ============================================================
def chamar_gemini(prompt_ia):
    if not GEMINI_KEY:
        return None
    modelos = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
    for modelo in modelos:
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/" + modelo + ":generateContent?key=" + GEMINI_KEY
            body = {"contents": [{"role": "user", "parts": [{"text": prompt_ia}]}]}
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode())
            return d["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            continue
    return None


def chamar_groq(prompt_ia):
    if not GROQ_KEY:
        return None
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        body = {"model": "openai/gpt-oss-120b",
                "messages": [{"role": "user", "content": prompt_ia}],
                "temperature": 0.7}
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + GROQ_KEY, "Content-Type": "application/json", "User-Agent": UA},
            method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
        return d["choices"][0]["message"]["content"]
    except Exception:
        return None


def chamar_ia(prompt_ia, ia):
    if ia == "groq":
        return chamar_groq(prompt_ia)
    return chamar_gemini(prompt_ia)


def montar_contexto(ia, limite):
    linhas = []
    for h in HISTORICO[-limite:]:
        quem = h.get("quem", "IA")
        linhas.append("USER: " + h["user"])
        linhas.append(quem.upper() + ": " + h["ia"])
    return "\n".join(linhas)


def ia_interpretar_pedido(msg, ia):
    limite = 3 if ia == "gemini" else 8
    contexto = montar_contexto(ia, limite)

    prompt = (
        "Voce decide quando usar ferramentas.\n\n"
        "FERRAMENTAS:\n"
        "- IMAGEM: gera imagens estaticas\n"
        "- VIDEO: gera videos com movimento (Gemini Omni)\n"
        "- CONVERSA: so texto\n\n"
        "Responda APENAS com JSON:\n"
        '{"acao":"imagem|video|conversa","prompt":"prompt em ingles detalhado","duracao":5,"comentario":"mensagem em PT"}\n\n'
        "Exemplos:\n"
        'Usuario: "cria um video de gato correndo"\n'
        '{"acao":"video","prompt":"a cute cat running fast on green grass, dynamic action, cinematic","duracao":5,"comentario":"Vou criar um video do gatinho correndo!"}\n\n'
        'Usuario: "faz uma imagem de por do sol"\n'
        '{"acao":"imagem","prompt":"beautiful sunset over mountains, cinematic","duracao":0,"comentario":"Vou gerar uma imagem!"}\n\n'
        'Usuario: "oi tudo bem"\n'
        '{"acao":"conversa","prompt":"","duracao":0,"comentario":""}\n\n'
        "Historico:\n" + contexto + "\n\n"
        "Usuario: " + msg + "\n"
        "JSON:"
    )
    resp = chamar_ia(prompt, ia)
    if not resp:
        return {"acao": "conversa"}

    try:
        m = re.search(r'\{.*\}', resp, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return json.loads(resp)
    except Exception:
        return {"acao": "conversa"}


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
    decisao = ia_interpretar_pedido(msg, ia)
    acao = decisao.get("acao", "conversa")
    comentario = decisao.get("comentario", "")
    prompt_f = decisao.get("prompt", msg)
    duracao = decisao.get("duracao", 5)

    print("[ia] " + ia + " -> " + acao)

    if acao == "imagem":
        nome, err = ferramenta_imagem(prompt_f)
        resp = (comentario + " Imagem gerada!") if not err else ("Erro: " + err)
        item = {"user": msg, "ia": resp, "quem": ia.capitalize(), "tipo": "imagem", "midia": nome if not err else None}
        HISTORICO.append(item)
        return jsonify({"ok": True, "resposta": resp, "ia": ia.capitalize(), "tipo": "imagem", "midia": item["midia"]})

    if acao == "video":
        nome, err, ferramenta = gerar_video(prompt_f, duracao)
        resp = (comentario + " Video gerado com " + (ferramenta or "?")) if not err else ("Erro: " + err)
        item = {"user": msg, "ia": resp, "quem": ia.capitalize(), "tipo": "video", "midia": nome if not err else None}
        HISTORICO.append(item)
        return jsonify({"ok": True, "resposta": resp, "ia": ia.capitalize(), "tipo": "video", "midia": item["midia"]})

    limite = 3 if ia == "gemini" else 8
    contexto = montar_contexto(ia, limite)
    sys_inst = "Voce e uma IA pessoal chamada " + ia.capitalize() + ". Responda em portugues BR."
    prompt_final = sys_inst + "\n\nHistorico:\n" + contexto + "\n\nUSER: " + msg + "\nASSISTANT:"

    resp = chamar_ia(prompt_final, ia)
    if resp:
        HISTORICO.append({"user": msg, "ia": resp, "quem": ia.capitalize()})
        return jsonify({"ok": True, "resposta": resp, "ia": ia.capitalize()})
    return jsonify({"erro": "IA nao respondeu"}), 500


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
