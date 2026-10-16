"""
app.py — Servidor Flask do YouTube Shorts Bot
Recebe links, roda o criar.py, e mostra o status em tempo real.
"""
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, redirect, url_for

BASE = Path(__file__).parent
MODULOS = BASE / "modulos"
TEMP = BASE / "temp"
TEMP.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

# Fila de jobs em memória (some quando o servidor reinicia)
JOBS = {}
HISTORICO = []


# ============================================================
# HELPERS
# ============================================================
def rodar_criar(url_baixo, job_id):
    """Roda o criar.py em background e vai atualizando o status."""
    try:
        JOBS[job_id]["status"] = "rodando"
        JOBS[job_id]["progresso"] = 5
        JOBS[job_id]["msg"] = "Baixando vídeo do topo..."

        # Copia o criar.py pros modulos (garante que tá atualizado)
        # (Aqui você poderia ter uma versão adaptada pra web)

        # Por enquanto, só simula (você vai adaptar depois)
        passos = [
            (10, "Baixando vídeo do topo..."),
            (20, "Baixando vídeo de reação..."),
            (35, "Extraindo frames..."),
            (50, "Analisando rostos com 4 IAs..."),
            (65, "Gerando título e hashtags..."),
            (75, "Criando faixa de texto..."),
            (90, "Montando vídeo final..."),
            (98, "Finalizando..."),
            (100, "Concluído!"),
        ]

        for pct, msg in passos:
            time.sleep(1.5)  # Simula o tempo de cada passo
            JOBS[job_id]["progresso"] = pct
            JOBS[job_id]["msg"] = msg

        JOBS[job_id]["status"] = "concluido"
        JOBS[job_id]["video"] = "/sdcard/Download/criar_simulado.mp4"
        JOBS[job_id]["titulo"] = "Chris e parceiro mandando o passinho ⚽ #Shorts"
        JOBS[job_id]["frase"] = "DUPLA DINÂMICA"

        # Salva no histórico
        HISTORICO.append({
            "id": job_id,
            "url": url_baixo,
            "titulo": JOBS[job_id]["titulo"],
            "frase": JOBS[job_id]["frase"],
            "data": datetime.now().isoformat(),
            "status": "concluido",
        })

    except Exception as e:
        JOBS[job_id]["status"] = "erro"
        JOBS[job_id]["msg"] = str(e)


# ============================================================
# ROTAS
# ============================================================
@app.route("/")
def index():
    return render_template("index.html", historico=HISTORICO[-10:])


@app.route("/criar", methods=["POST"])
def criar():
    url_baixo = request.form.get("url_baixo", "").strip()
    if not url_baixo:
        return jsonify({"erro": "Link obrigatório"}), 400

    job_id = str(uuid.uuid4())[:8]
    JOBS[job_id] = {
        "id": job_id,
        "url": url_baixo,
        "status": "iniciando",
        "progresso": 0,
        "msg": "Iniciando...",
        "iniciado": datetime.now().isoformat(),
    }

    # Roda em background
    t = threading.Thread(target=rodar_criar, args=(url_baixo, job_id))
    t.daemon = True
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    if job_id not in JOBS:
        return jsonify({"erro": "Job não encontrado"}), 404
    return jsonify(JOBS[job_id])


@app.route("/historico")
def historico():
    return jsonify(HISTORICO[-20:])


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("  🎬 YOUTUBE SHORTS BOT")
    print(f"  Rodando em http://localhost:{porta}")
    print("=" * 50)
    app.run(host="0.0.0.0", port=porta, debug=False)
