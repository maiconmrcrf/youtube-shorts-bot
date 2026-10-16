"""
app.py — Chat com 2 IAs (Gemini + Groq) + geração de imagem/vídeo com ferramentas grátis.
"""
import base64
import json
import os
import re
import time
import urllib.request
import urllib.parse
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

app = Flask(__name__)

GEMINI_KEY = os.environ.get("GEMINI_KEY_IA", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_KEY   = os.environ.get("GROQ_API_KEY", "").strip()
CF_ACCOUNT = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
CF_TOKEN   = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
POLL_KEY   = os.environ.get("POLLINATIONS_API_KEY", "").strip()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

HISTORICO = []
IA_ATIVA = "gemini"

MIDIA = Path(__file__).parent / "midia"
MIDIA.mkdir(parents=True, exist_ok=True)

# Modelos Gemini REAIS (verificados na doc oficial)
MODELOS_GEMINI = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]

# Modelos de vídeo Omni (endpoint Interactions API, NÃO generateContent)
MODELOS_OMNI = [
    "gemini-omni-1.1-flash",
    "gemini-omni-flash-preview",
]


# ============================================================
# IMAGEM GRÁTIS
# ============================================================

def imagem_pollinations(prompt):
    """Pollinations: grátis, sem chave. Com chave = mais rápido/sem fila."""
    prompt_enc = urllib.parse.quote(prompt, safe="")
    base = "https://image.pollinations.ai/prompt/" + prompt_enc
    params = "?model=flux&width=1024&height=1024&nologo=true"
    if POLL_KEY:
        params += "&key=" + POLL_KEY
    url = base + params
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=90) as r:
            img_bytes = r.read()
            if len(img_bytes) > 1000:
                nome = "img_poll_" + uuid.uuid4().hex[:8] + ".jpg"
                (MIDIA / nome).write_bytes(img_bytes)
                return nome, None
    except Exception as e:
        return None, "pollinations: " + str(e)[:80]
    return None, "pollinations: resposta vazia"


def imagem_cloudflare(prompt):
    """Cloudflare Workers AI — FLUX.1 Schnell (free tier)."""
    if not (CF_ACCOUNT and CF_TOKEN):
        return None, "sem chave Cloudflare"
    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        + CF_ACCOUNT
        + "/ai/run/@cf/black-forest-labs/flux-1-schnell"
    )
    body = json.dumps({"prompt": prompt, "steps": 4}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": "Bearer " + CF_TOKEN,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
        if d.get("success"):
            img_bytes = base64.b64decode(d["result"]["image"])
            nome = "img_cf_" + uuid.uuid4().hex[:8] + ".jpg"
            (MIDIA / nome).write_bytes(img_bytes)
            return nome, None
        return None, "cloudflare: " + str(d.get("errors", "erro desconhecido"))[:80]
    except Exception as e:
        return None, "cloudflare: " + str(e)[:80]


def imagem_picsum(prompt):
    """Picsum Photos: placeholder grátis como último recurso (NÃO usa o prompt)."""
    try:
        seed = uuid.uuid4().hex[:8]
        url = "https://picsum.photos/seed/" + seed + "/1024/1024"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            img_bytes = r.read()
        nome = "img_picsum_" + uuid.uuid4().hex[:8] + ".jpg"
        (MIDIA / nome).write_bytes(img_bytes)
        return nome, None
    except Exception as e:
        return None, "picsum: " + str(e)[:80]


def ferramenta_imagem(prompt):
    """Tenta ferramentas grátis em cascata."""
    # 1) Pollinations (melhor qualidade, grátis)
    nome, err = imagem_pollinations(prompt)
    if nome:
        return nome, None, "Pollinations"

    # 2) Cloudflare Workers AI (se tiver chave)
    nome, err = imagem_cloudflare(prompt)
    if nome:
        return nome, None, "Cloudflare FLUX"

    # 3) Picsum (último recurso, aleatório)
    nome, err = imagem_picsum(prompt)
    if nome:
        return nome, None, "Picsum (placeholder)"

    return None, "Todas as APIs de imagem falharam: " + err, None


# ============================================================
# VÍDEO GRÁTIS
# ============================================================

def video_omni_interactions(prompt, duracao=5):
    """
    Gemini Omni Flash via Interactions API.
    Endpoint CORRETO: POST /v1beta/interactions
    NÃO funciona com generateContent — só com interactions.create.
    """
    if not GEMINI_KEY:
        return None, "sem chave Gemini"

    for modelo in MODELOS_OMNI:
        try:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/interactions?key="
                + GEMINI_KEY
            )
            body = {
                "model": modelo,
                "input": prompt,
                "response_format": {
                    "aspect_ratio": "9:16",
                    "duration": duracao,
                    "resolution": "720p",
                },
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read().decode())

            # Omni retorna inline base64
            output = d.get("output_video") or d.get("outputVideo")
            if output and output.get("data"):
                vid_bytes = base64.b64decode(output["data"])
                nome = "vid_omni_" + uuid.uuid4().hex[:8] + ".mp4"
                (MIDIA / nome).write_bytes(vid_bytes)
                return nome, None

            # Às vezes vem via Files API URI
            if output and output.get("uri"):
                vid_req = urllib.request.Request(
                    output["uri"], headers={"x-goog-api-key": GEMINI_KEY}
                )
                with urllib.request.urlopen(vid_req, timeout=120) as r:
                    vid_bytes = r.read()
                nome = "vid_omni_" + uuid.uuid4().hex[:8] + ".mp4"
                (MIDIA / nome).write_bytes(vid_bytes)
                return nome, None

        except Exception as e:
            print("[omni] " + modelo + " falhou: " + str(e)[:80])

    return None, "Gemini Omni falhou"


def video_kenburns(prompt, duracao=5):
    """Fallback grátis: imagem → vídeo com zoom (Ken Burns) via ffmpeg."""
    nome_img, err, _ = ferramenta_imagem(prompt)
    if err:
        return None, "imagem falhou: " + err

    img_path = MIDIA / nome_img
    nome_vid = "vid_kb_" + uuid.uuid4().hex[:8] + ".mp4"
    caminho = MIDIA / nome_vid

    import shutil
    import subprocess

    if not shutil.which("ffmpeg"):
        return None, "ffmpeg não instalado"

    # Força 25fps no input para duração correta
    fps = 25
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(img_path),
        "-t", str(duracao),
        "-r", str(fps),
        "-vf", (
            "zoompan=z='min(zoom+0.0015,1.5)':d="
            + str(duracao * fps)
            + ":s=720x1280,format=yuv420p"
        ),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        str(caminho),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return nome_vid, None
    except Exception as e:
        return None, "ffmpeg falhou: " + str(e)[:80]


def gerar_video(prompt, duracao=5):
    """Tenta Omni → Ken Burns (ambos grátis)."""
    print("[video] tentando Gemini Omni (Interactions API)...")
    res, err = video_omni_interactions(prompt, duracao)
    if res:
        return res, None, "Gemini Omni"

    print("[video] Omni falhou, usando Ken Burns grátis...")
    res, err = video_kenburns(prompt, duracao)
    if res:
        return res, None, "Imagem + Ken Burns"

    return None, "Todas as ferramentas de vídeo falharam: " + err, None


# ============================================================
# IA — Gemini
# ============================================================

def chamar_gemini(prompt_ia):
    if not GEMINI_KEY:
        return None
    for modelo in MODELOS_GEMINI:
        try:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                + modelo + ":generateContent?key=" + GEMINI_KEY
            )
            body = {"contents": [{"role": "user", "parts": [{"text": prompt_ia}]}]}
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode())
            return d["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            continue
    return None


# ============================================================
# IA — Groq (OpenAI-compatible)
# ============================================================

def chamar_groq(prompt_ia):
    if not GROQ_KEY:
        return None
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        body = {
            "model": "openai/gpt-oss-120b",
            "messages": [{"role": "user", "content": prompt_ia}],
            "temperature": 0.7,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + GROQ_KEY,
                "Content-Type": "application/json",
                "User-Agent": UA,
            },
            method="POST",
        )
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


# ============================================================
# DECISÃO DE FERRAMENTA (a IA escolhe)
# ============================================================

def ia_interpretar_pedido(msg, ia):
    limite = 3 if ia == "gemini" else 8
    contexto = montar_contexto(ia, limite)

    prompt = (
        "Voce decide quando usar ferramentas.\n\n"
        "FERRAMENTAS DISPONIVEIS (todas gratis):\n"
        "- IMAGEM: gera imagens estaticas (Pollinations/Cloudflare FLUX)\n"
        "- VIDEO: gera videos de 3-6 segundos (Gemini Omni ou Ken Burns)\n"
        "- CONVERSA: so texto\n\n"
        "Responda APENAS com JSON:\n"
        '{"acao":"imagem|video|conversa","prompt":"prompt em ingles detalhado","duracao":5,"comentario":"mensagem em PT"}\n\n'
        "Exemplos:\n"
        'Usuario: "cria um video de gato correndo"\n'
        '{"acao":"video","prompt":"a cute cat running on grass, cinematic action","duracao":5,"comentario":"Vou criar um video!"}\n\n'
        'Usuario: "faz uma imagem de por do sol"\n'
        '{"acao":"imagem","prompt":"beautiful sunset over mountains","duracao":0,"comentario":"Vou gerar uma imagem!"}\n\n'
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

    # ---- IMAGEM ----
    if acao == "imagem":
        nome, err, ferramenta = ferramenta_imagem(prompt_f)
        if err:
            resp = "Erro: " + err
        else:
            resp = (comentario + " Imagem gerada com " + ferramenta + "!").strip()
        item = {
            "user": msg, "ia": resp, "quem": ia.capitalize(),
            "tipo": "imagem", "midia": nome if not err else None,
            "ferramenta": ferramenta if not err else None,
        }
        HISTORICO.append(item)
        return jsonify({
            "ok": True, "resposta": resp, "ia": ia.capitalize(),
            "tipo": "imagem", "midia": item["midia"],
            "ferramenta": item["ferramenta"],
        })

    # ---- VIDEO ----
    if acao == "video":
        nome, err, ferramenta = gerar_video(prompt_f, duracao)
        if err:
            resp = "Erro: " + err
        else:
            resp = (comentario + " Video gerado com " + ferramenta + "!").strip()
        item = {
            "user": msg, "ia": resp, "quem": ia.capitalize(),
            "tipo": "video", "midia": nome if not err else None,
            "ferramenta": ferramenta if not err else None,
        }
        HISTORICO.append(item)
        return jsonify({
            "ok": True, "resposta": resp, "ia": ia.capitalize(),
            "tipo": "video", "midia": item["midia"],
            "ferramenta": item["ferramenta"],
        })

    # ---- CONVERSA ----
    limite = 3 if ia == "gemini" else 8
    contexto = montar_contexto(ia, limite)
    sys_inst = "Voce e uma IA pessoal chamada " + ia.capitalize() + ". Responda em portugues BR."
    prompt_final = sys_inst + "\n\nHistorico:\n" + contexto + "\n\nUSER: " + msg + "\nASSISTANT:"

    resp = chamar_ia(prompt_final, ia)

    if not resp:
        outra = "groq" if ia == "gemini" else "gemini"
        print("[fallback] " + ia + " falhou, tentando " + outra)
        resp = chamar_ia(prompt_final, outra)
        if resp:
            ia = outra

    if resp:
        HISTORICO.append({"user": msg, "ia": resp, "quem": ia.capitalize()})
        return jsonify({"ok": True, "resposta": resp, "ia": ia.capitalize()})
    return jsonify({"erro": "Nenhuma IA respondeu"}), 500


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




# ============================================================
# UPLOAD DE ARQUIVO
# ============================================================
@app.route("/upload", methods=["POST"])
def upload():
    if "arquivo" not in request.files:
        return jsonify({"erro": "Nenhum arquivo enviado"}), 400

    arquivo = request.files["arquivo"]
    if not arquivo.filename:
        return jsonify({"erro": "Nome de arquivo vazio"}), 400

    nome_seguro = secure_filename(arquivo.filename)
    ext = Path(nome_seguro).suffix.lower()
    nome_unico = uuid.uuid4().hex[:8] + "_" + nome_seguro
    caminho = MIDIA / nome_unico
    arquivo.save(str(caminho))

    tamanho = caminho.stat().st_size
    print("[upload] " + nome_unico + " (" + str(tamanho) + " bytes)")

    # Detecta o tipo e analisa
    ia = request.form.get("ia", "gemini").lower()
    descricao = "Arquivo recebido: " + nome_seguro + " (" + str(tamanho) + " bytes)"

    # Se for imagem, tenta analisar com Gemini
    if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"] and GEMINI_KEY:
        try:
            import base64 as b64
            img_b64 = b64.b64encode(caminho.read_bytes()).decode("ascii")

            prompt = (
                "Analise esta imagem detalhadamente em portugues BR, com foco especial em pessoas e rostos:\n"
                "1) Quantas pessoas aparecem? Faixa etaria e genero aparente de cada uma.\n"
                "2) Descreva CADA ROSTO: expressao facial (sorrindo, serio, surpreso, triste), emocao transmitida, direcao do olhar.\n"
                "3) Caracteristicas fisicas: cor de pele, cabelo (cor, comprimento, estilo), olhos, barba/bigode.\n"
                "4) Acessorios: bone, oculos, brinco, corrente, tatuagem.\n"
                "5) Posicionamento (esquerda/direita/centro) e roupas.\n"
                "6) Cenario de fundo, objetos relevantes e cores predominantes.\n"
                "7) Texto visivel (se houver).\n\n"
                "Seja MUITO detalhado sobre expressoes e caracteristicas faciais. Se reconhecer alguem famoso com certeza (90%+), diga o nome. Nao invente."
            )

            modelos = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
            for modelo in modelos:
                try:
                    url = "https://generativelanguage.googleapis.com/v1beta/models/" + modelo + ":generateContent?key=" + GEMINI_KEY
                    body = {"contents": [{"role": "user", "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                    ]}]}
                    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                        headers={"Content-Type": "application/json"}, method="POST")
                    with urllib.request.urlopen(req, timeout=90) as r:
                        d = json.loads(r.read().decode())
                    descricao = d["candidates"][0]["content"]["parts"][0]["text"]
                    break
                except Exception as e:
                    print("[upload img] " + modelo + " falhou: " + str(e)[:80])
        except Exception as e:
            descricao = "Imagem salva, mas nao consegui analisar: " + str(e)[:100]

    # Se for PDF, avisa
    elif ext == ".pdf":
        descricao = "PDF recebido: " + nome_seguro + ". Tamanho: " + str(round(tamanho/1024, 1)) + " KB. Ainda nao consigo ler PDF completo, mas posso tentar se voce descrever o conteudo."

    # Se for video, avisa
    elif ext in [".mp4", ".mov", ".avi", ".webm", ".mkv"]:
        descricao = "Video recebido: " + nome_seguro + ". Tamanho: " + str(round(tamanho/1024/1024, 1)) + " MB. Ainda nao consigo assistir video, mas posso tentar se voce descrever."

    # Se for texto, lê
    elif ext in [".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".css"]:
        try:
            conteudo = caminho.read_text(encoding="utf-8", errors="ignore")[:2000]
            descricao = "Arquivo de texto lido:\n\n" + conteudo
        except Exception:
            descricao = "Arquivo salvo, mas nao consegui ler."

    item = {
        "user": "📎 " + nome_seguro,
        "ia": descricao,
        "quem": "IA",
        "tipo": "imagem" if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"] else "arquivo",
        "midia": nome_unico if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov"] else None,
    }
    HISTORICO.append(item)

    return jsonify({
        "ok": True,
        "resposta": descricao,
        "ia": "IA",
        "tipo": item["tipo"],
        "midia": item["midia"],
        "arquivo": nome_unico,
    })


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
