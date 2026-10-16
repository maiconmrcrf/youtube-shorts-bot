"""
app.py — Chat com 2 IAs + ferramentas (imagem/video) em cascata.
A IA interpreta o pedido, refina o prompt, escolhe a ferramenta e executa.
"""
import base64
import json
import os
import re
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


# ============================================================
# FERRAMENTAS
# ============================================================
def ferramenta_imagem(prompt):
    """Cloudflare FLUX."""
    if not CF_ACCOUNT or not CF_TOKEN:
        return None, "Cloudflare nao configurado"
    url = "https://api.cloudflare.com/client/v4/accounts/" + CF_ACCOUNT + "/ai/run/@cf/black-forest-labs/flux-1-schnell"
    body = json.dumps({"prompt": prompt, "steps": 4}).encode()
    req = urllib.request.Request(url, data=body,
        headers={"Authorization": "Bearer " + CF_TOKEN, "Content-Type": "application/json"}, method="POST")
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
        return None, str(e)[:80]


def ferramenta_video_magichour(prompt, duracao=5):
    if not MH_KEY:
        return None, "sem chave"
    url = "https://api.magichour.ai/v1/text-to-video"
    body = json.dumps({
        "end_seconds": duracao, "aspect_ratio": "9:16", "resolution": "480p",
        "model": "ltx-2.5", "style": {"prompt": prompt}
    }).encode()
    try:
        req = urllib.request.Request(url, data=body,
            headers={"Authorization": "Bearer " + MH_KEY, "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
        job_id = d.get("id")
        if not job_id:
            return None, "sem id"
        for _ in range(36):
            time.sleep(5)
            req2 = urllib.request.Request("https://api.magichour.ai/v1/video-projects/" + job_id,
                headers={"Authorization": "Bearer " + MH_KEY}, method="GET")
            with urllib.request.urlopen(req2, timeout=30) as r2:
                s = json.loads(r2.read().decode())
            if s.get("status") == "complete":
                url_vid = s.get("download", {}).get("url")
                if url_vid:
                    nome = "vid_" + uuid.uuid4().hex[:8] + ".mp4"
                    urllib.request.urlretrieve(url_vid, MIDIA / nome)
                    return nome, None
                return None, "sem url"
            elif s.get("status") in ("error", "failed"):
                return None, "falhou"
        return None, "timeout"
    except Exception as e:
        return None, str(e)[:80]


def ferramenta_video_replicate(prompt, duracao=5):
    if not REPLICATE_KEY:
        return None, "sem chave"
    url = "https://api.replicate.com/v1/predictions"
    body = json.dumps({
        "version": "9f747673945c62801b13b84701c783929c0ee784e4748ec062204894dda1a351",
        "input": {"prompt": prompt}
    }).encode()
    try:
        req = urllib.request.Request(url, data=body,
            headers={"Authorization": "Token " + REPLICATE_KEY, "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
        pred_id = d.get("id")
        if not pred_id:
            return None, "sem id"
        for _ in range(36):
            time.sleep(5)
            req2 = urllib.request.Request("https://api.replicate.com/v1/predictions/" + pred_id,
                headers={"Authorization": "Token " + REPLICATE_KEY}, method="GET")
            with urllib.request.urlopen(req2, timeout=30) as r2:
                s = json.loads(r2.read().decode())
            if s.get("status") == "succeeded":
                output = s.get("output")
                url_vid = output if isinstance(output, str) else (output[0] if output else None)
                if url_vid:
                    nome = "vid_" + uuid.uuid4().hex[:8] + ".mp4"
                    urllib.request.urlretrieve(url_vid, MIDIA / nome)
                    return nome, None
                return None, "sem url"
            elif s.get("status") == "failed":
                return None, "falhou"
        return None, "timeout"
    except Exception as e:
        return None, str(e)[:80]


def ferramenta_video(prompt, duracao=5):
    """Cascata de ferramentas de video."""
    for nome, func in [("Magic Hour", ferramenta_video_magichour),
                       ("Replicate", ferramenta_video_replicate)]:
        print("[video] tentando " + nome + "...")
        res, err = func(prompt, duracao)
        if res:
            return res, None, nome
        print("[video] " + nome + " falhou: " + str(err))
    return None, "Todas falharam", None


# ============================================================
# IA INTERMEDIÁRIA (decide quando chamar ferramenta)
# ============================================================
def chamar_ia(prompt_ia, ia="gemini"):
    if ia == "groq":
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
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode())
            return d["choices"][0]["message"]["content"]
        except Exception:
            return None
    else:
        if not GEMINI_KEY:
            return None
        modelos = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash",
                   "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"]
        for modelo in modelos:
            try:
                url = "https://generativelanguage.googleapis.com/v1beta/models/" + modelo + ":generateContent?key=" + GEMINI_KEY
                body = {"contents": [{"role": "user", "parts": [{"text": prompt_ia}]}]}
                req = urllib.request.Request(url, data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=90) as r:
                    d = json.loads(r.read().decode())
                return d["candidates"][0]["content"]["parts"][0]["text"]
            except Exception:
                continue
        return None


def ia_interpretar_pedido(msg, ia):
    """A IA analisa o pedido e retorna JSON com a acao."""
    prompt = (
        "Voce e uma IA que decide quando usar ferramentas. Analise a mensagem do usuario.\n\n"
        "Ferramentas disponiveis:\n"
        "- IMAGEM: gera imagens (Cloudflare FLUX)\n"
        "- VIDEO: gera videos de 3-6 segundos (Magic Hour/Replicate)\n"
        "- CONVERSA: so responde texto\n\n"
        "Responda SOMENTE com JSON valido:\n"
        '{"acao": "imagem|video|conversa", "prompt": "prompt limpo e detalhado em ingles", "duracao": 5, "comentario": "o que vai fazer"}\n\n'
        "Exemplo:\n"
        'Usuario: "cria um video de um gato correndo por 5 segundos"\n'
        'Resposta: {"acao": "video", "prompt": "a cute cat running on grass, cinematic, 5 seconds", "duracao": 5, "comentario": "Vou criar um video do gatinho correndo!"}\n\n'
        "Agora responda para:\n"
        'Usuario: "' + msg + '"\n'
    )
    resp = chamar_ia(prompt, ia)
    if not resp:
        return {"acao": "conversa"}

    # Extrai JSON
    try:
        return json.loads(resp)
    except Exception:
        m = re.search(r'\{.*\}', resp, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {"acao": "conversa"}


# ============================================================
# HISTÓRICO
# ============================================================
def montar_contexto():
    msgs = []
    for h in HISTORICO[-15:]:
        quem = h.get("quem", "IA")
        msgs.append({"role": "user", "content": h["user"]})
        msgs.append({"role": "assistant", "content": "[" + quem + "]: " + h["ia"]})
    return msgs


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

    # 1) IA interpreta o pedido
    decisao = ia_interpretar_pedido(msg, ia)
    acao = decisao.get("acao", "conversa")
    comentario = decisao.get("comentario", "")
    prompt_ferramenta = decisao.get("prompt", msg)
    duracao = decisao.get("duracao", 5)

    print("[ia] acao=" + acao + " | prompt=" + prompt_ferramenta[:60])

    # 2) Se for ferramenta, chama
    if acao == "imagem":
        nome, err = ferramenta_imagem(prompt_ferramenta)
        resp = (comentario + " ✅ Imagem gerada!") if not err else ("Erro: " + err)
        item = {"user": msg, "ia": resp, "quem": ia.capitalize(), "tipo": "imagem", "midia": nome if not err else None}
        HISTORICO.append(item)
        return jsonify({"ok": True, "resposta": resp, "ia": ia.capitalize(), "tipo": "imagem", "midia": item["midia"]})

    if acao == "video":
        nome, err, ferramenta = ferramenta_video(prompt_ferramenta, duracao)
        resp = (comentario + " ✅ Video gerado com " + (ferramenta or "?")) if not err else ("Erro: " + err)
        item = {"user": msg, "ia": resp, "quem": ia.capitalize(), "tipo": "video", "midia": nome if not err else None}
        HISTORICO.append(item)
        return jsonify({"ok": True, "resposta": resp, "ia": ia.capitalize(), "tipo": "video", "midia": item["midia"]})

    # 3) Conversa normal
    contexto = montar_contexto()
    sys_inst = ("Voce e uma IA pessoal amigavel chamada " + ia.capitalize() +
                ". Responda em portugues BR. Mensagens marcadas com [outra_ia] foram dadas por outra IA.")
    prompt_final = sys_inst + "\n\n"
    for c in contexto:
        prompt_final += c["role"].upper() + ": " + c["content"] + "\n"
    prompt_final += "USER: " + msg + "\nASSISTANT:"

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
