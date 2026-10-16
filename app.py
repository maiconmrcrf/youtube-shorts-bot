"""
app.py — Chat com 2 IAs + ferramentas em ROTAÇÃO.
Cada video usa uma ferramenta diferente (Magic Hour -> Replicate -> HuggingFace -> volta).
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
HF_TOKEN       = os.environ.get("HUGGINGFACE_TOKEN", "").strip()
MH_KEY         = os.environ.get("MAGIC_HOUR_API_KEY", "").strip()
REPLICATE_KEY  = os.environ.get("REPLICATE_API_TOKEN", "").strip()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

HISTORICO = []
IA_ATIVA = "gemini"

# Rotação de ferramentas
ROTACAO = ["magichour", "replicate", "huggingface"]
INDICE_ROTACAO = 0

MIDIA = Path("/tmp/midia_ia")
MIDIA.mkdir(parents=True, exist_ok=True)


# ============================================================
# FERRAMENTAS DE IMAGEM
# ============================================================
def ferramenta_imagem(prompt):
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


# ============================================================
# FERRAMENTAS DE VIDEO
# ============================================================
def video_magichour(prompt, duracao=5):
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


def video_replicate(prompt, duracao=5):
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


def video_huggingface(prompt, duracao=5):
    """Hugging Face - usa Space publico (gratis)."""
    if not HF_TOKEN:
        return None, "sem chave"
    # Implementacao simples via Space do AnimateDiff
    # (pode falhar - fallback pra outros)
    return None, "nao implementado"


FERRAMENTAS_VIDEO = {
    "magichour": video_magichour,
    "replicate": video_replicate,
    "huggingface": video_huggingface,
}


def proxima_ferramenta():
    """Rotaciona entre as ferramentas disponiveis."""
    global INDICE_ROTACAO
    # Pula ferramentas sem chave configurada
    for _ in range(3):
        ferramenta = ROTACAO[INDICE_ROTACAO]
        INDICE_ROTACAO = (INDICE_ROTACAO + 1) % len(ROTACAO)
        # Verifica se tem chave
        if ferramenta == "magichour" and MH_KEY:
            return ferramenta
        if ferramenta == "replicate" and REPLICATE_KEY:
            return ferramenta
        if ferramenta == "huggingface" and HF_TOKEN:
            return ferramenta
    return None


def gerar_video_rotacao(prompt, duracao=5):
    """Tenta a ferramenta da vez. Se falhar, tenta a proxima."""
    tentativas = 0
    while tentativas < len(ROTACAO):
        nome_ferramenta = proxima_ferramenta()
        if not nome_ferramenta:
            tentativas += 1
            continue
        func = FERRAMENTAS_VIDEO[nome_ferramenta]
        print("[video] tentando " + nome_ferramenta)
        res, err = func(prompt, duracao)
        if res:
            return res, None, nome_ferramenta
        print("[video] " + nome_ferramenta + " falhou: " + str(err))
        tentativas += 1
    return None, "Todas as ferramentas falharam", None


# ============================================================
# IA
# ============================================================
def chamar_gemini(prompt_ia):
    """Gemini rapido - poucos modelos, timeout curto."""
    if not GEMINI_KEY:
        return None
    modelos = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]  # 2 modelos rapidos
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
    """Monta o contexto com o limite de linhas especifico da IA."""
    linhas = []
    for h in HISTORICO[-limite:]:
        quem = h.get("quem", "IA")
        linhas.append("USER: " + h["user"])
        linhas.append(quem.upper() + ": " + h["ia"])
    return "\n".join(linhas)


def ia_interpretar_pedido(msg, ia):
    """IA rapida pra decidir acao. Gemini le 3 linhas, Groq le 8."""
    # Contexto limitado (Gemini 3, Groq 8)
    limite = 3 if ia == "gemini" else 8
    contexto = montar_contexto(ia, limite)

    prompt = (
        "Voce decide quando usar ferramentas. Responda APENAS com JSON.\n"
        "Ferramentas: IMAGEM (imagens), VIDEO (3-6s), CONVERSA (texto).\n"
        "JSON: {\"acao\":\"imagem|video|conversa\",\"prompt\":\"prompt em ingles\",\"duracao\":5,\"comentario\":\"o que vai fazer\"}\n\n"
        "Historico recente:\n" + contexto + "\n\n"
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

    # IA decide
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
        nome, err, ferramenta = gerar_video_rotacao(prompt_f, duracao)
        resp = (comentario + " Video gerado com " + (ferramenta or "?")) if not err else ("Erro: " + err)
        item = {"user": msg, "ia": resp, "quem": ia.capitalize(), "tipo": "video", "midia": nome if not err else None, "ferramenta": ferramenta}
        HISTORICO.append(item)
        return jsonify({"ok": True, "resposta": resp, "ia": ia.capitalize(), "tipo": "video", "midia": item["midia"]})

    # Conversa
    limite = 3 if ia == "gemini" else 8
    contexto = montar_contexto(ia, limite)

    sys_inst = "Voce e uma IA pessoal chamada " + ia.capitalize() + ". Responda em portugues BR de forma direta."
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
