"""
app.py — Servidor Flask do YouTube Shorts Bot
Usa o criar.py ORIGINAL do Termux (que já funciona).
"""
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file

BASE = Path(__file__).parent
MODULOS = BASE / "modulos"
TEMP = BASE / "temp"
TEMP.mkdir(parents=True, exist_ok=True)

# Pasta onde o criar.py original salva (pode ser ~/yt/temp)
TEMP_ORIGINAL = MODULOS / "temp"

app = Flask(__name__)

JOBS = {}
HISTORICO = []


def rodar_criar(url_baixo, job_id):
    """Roda o criar.py original, mandando o link via stdin."""
    try:
        JOBS[job_id]["status"] = "rodando"
        JOBS[job_id]["progresso"] = 0
        JOBS[job_id]["msg"] = "Iniciando..."

        # Usa o criar.py ORIGINAL (que funciona)
        script = MODULOS / "criar.py"
        if not script.exists():
            JOBS[job_id]["status"] = "erro"
            JOBS[job_id]["msg"] = "criar.py nao encontrado em modulos/"
            return

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        proc = subprocess.Popen(
            [sys.executable, "-u", str(script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=str(MODULOS),
        )

        # Manda o link
        proc.stdin.write(url_baixo + "\n")
        proc.stdin.flush()

        # Le a saida em tempo real
        buffer = ""
        for linha in proc.stdout:
            linha = linha.strip()
            buffer += linha + "\n"
            print(f"[criar] {linha}")

            # Extrai progresso
            m = re.search(r"(\d+)%", linha)
            if m:
                pct = int(m.group(1))
                JOBS[job_id]["progresso"] = pct

            # Pega a mensagem
            if linha and len(linha) < 200:
                JOBS[job_id]["msg"] = linha

            # Se pedir input de "s/n", manda "n"
            if "Subir pro YouTube" in linha or "(s/n)" in linha:
                try:
                    proc.stdin.write("n\n")
                    proc.stdin.flush()
                except Exception:
                    pass

        proc.wait()

        # Le o publicacao.json
        pub = MODULOS / "publicacao.json"
        if pub.exists():
            dados = json.loads(pub.read_text(encoding="utf-8"))
            JOBS[job_id]["status"] = "concluido"
            JOBS[job_id]["progresso"] = 100
            JOBS[job_id]["msg"] = "Concluído!"
            JOBS[job_id]["titulo"] = dados.get("titulo", "")
            JOBS[job_id]["descricao"] = dados.get("descricao", "")
            JOBS[job_id]["tags"] = dados.get("tags", [])
            JOBS[job_id]["hashtags"] = dados.get("hashtags", "")
            JOBS[job_id]["frase"] = dados.get("frase_curta", "")
            JOBS[job_id]["video"] = dados.get("video", "")

            HISTORICO.append({
                "id": job_id,
                "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "titulo": dados.get("titulo", ""),
                "descricao": dados.get("descricao", ""),
                "tags": dados.get("tags", []),
                "hashtags": dados.get("hashtags", ""),
                "frase": dados.get("frase_curta", ""),
                "video": dados.get("video", ""),
                "status": "aguardando",
                "agendado_para": None,
            })
        else:
            JOBS[job_id]["status"] = "erro"
            JOBS[job_id]["msg"] = "publicacao.json nao gerado. Ultimas linhas: " + buffer[-300:]

    except Exception as e:
        JOBS[job_id]["status"] = "erro"
        JOBS[job_id]["msg"] = str(e)


def postar_video(job_id):
    try:
        JOBS[job_id]["status"] = "postando"
        JOBS[job_id]["msg"] = "Enviando pro YouTube..."

        script = MODULOS / "enviar_short.py"
        if not script.exists():
            JOBS[job_id]["status"] = "erro"
            JOBS[job_id]["msg"] = "enviar_short.py nao encontrado"
            return

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        proc = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, env=env,
            cwd=str(MODULOS),
        )

        saida = (proc.stdout + proc.stderr).lower()

        if proc.returncode == 0 and ("postado" in saida or "youtu.be" in saida):
            JOBS[job_id]["status"] = "postado"
            JOBS[job_id]["msg"] = "Postado com sucesso!"
            for h in HISTORICO:
                if h["id"] == job_id:
                    h["status"] = "postado"
        elif "limit" in saida or "quota" in saida or "429" in saida or "403" in saida:
            JOBS[job_id]["status"] = "limite"
            JOBS[job_id]["msg"] = "Limite diario. Agende pra depois."
            for h in HISTORICO:
                if h["id"] == job_id:
                    h["status"] = "limite"
        else:
            JOBS[job_id]["status"] = "erro"
            JOBS[job_id]["msg"] = (proc.stdout + proc.stderr)[-200:]

    except Exception as e:
        JOBS[job_id]["status"] = "erro"
        JOBS[job_id]["msg"] = str(e)


def agendar_video(job_id, data_hora):
    for h in HISTORICO:
        if h["id"] == job_id:
            h["status"] = "agendado"
            h["agendado_para"] = data_hora
    JOBS[job_id]["status"] = "agendado"
    JOBS[job_id]["msg"] = f"Agendado pra {data_hora}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/criar", methods=["POST"])
def criar():
    url_baixo = request.form.get("url_baixo", "").strip()
    if not url_baixo:
        return jsonify({"erro": "Link obrigatorio"}), 400

    job_id = str(uuid.uuid4())[:8]
    JOBS[job_id] = {
        "id": job_id,
        "url": url_baixo,
        "status": "iniciando",
        "progresso": 0,
        "msg": "Iniciando...",
        "iniciado": datetime.now().isoformat(),
    }

    t = threading.Thread(target=rodar_criar, args=(url_baixo, job_id))
    t.daemon = True
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/postar/<job_id>", methods=["POST"])
def postar(job_id):
    if job_id not in JOBS:
        return jsonify({"erro": "Job nao encontrado"}), 404
    t = threading.Thread(target=postar_video, args=(job_id,))
    t.daemon = True
    t.start()
    return jsonify({"ok": True})


@app.route("/agendar/<job_id>", methods=["POST"])
def agendar(job_id):
    if job_id not in JOBS:
        return jsonify({"erro": "Job nao encontrado"}), 404
    data_hora = request.form.get("data_hora", "")
    if not data_hora:
        return jsonify({"erro": "Data obrigatoria"}), 400
    agendar_video(job_id, data_hora)
    return jsonify({"ok": True})


@app.route("/status/<job_id>")
def status(job_id):
    if job_id not in JOBS:
        return jsonify({"erro": "Job nao encontrado"}), 404
    return jsonify(JOBS[job_id])


@app.route("/historico")
def historico():
    return jsonify(HISTORICO[-20:])


@app.route("/video/<path:filename>")
def video(filename):
    # Procura em varias pastas
    for base in (MODULOS / "temp", TEMP):
        p = base / filename
        if p.exists():
            return send_file(str(p), mimetype="video/mp4")
    return jsonify({"erro": "Video nao encontrado"}), 404


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
