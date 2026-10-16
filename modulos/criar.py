import base64
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image, ImageDraw, ImageFont
from hashtags_db import pegar_tags
from gemini_http import gerar as gemini_gerar, extrair_json, _chamar

BASE = Path(__file__).parent.parent  # pasta do projeto
TEMP = BASE / "temp"
FONTES = BASE / "fontes"
PUBLICACAO = BASE / "publicacao.json"
FILA = BASE / "fila.json"

TEMP.mkdir(parents=True, exist_ok=True)
FONTES.mkdir(parents=True, exist_ok=True)

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODELO_PREFERIDO = "gemini-3.6-flash"

LINKS_TOPO = [
    "https://drive.google.com/file/d/1yxrqNn6m3EUE4ZVbN_2lyWFHaORUrE9e/view?usp=drivesdk",
    "https://drive.google.com/file/d/1e_G66S9IWPXjtgEHk_oVkrLt7PjtvKZ4/view?usp=drivesdk",
    "https://drive.google.com/file/d/1BjAPNffYWFl6Iow-hpq-Ntr2vPRLcxM8/view?usp=drivesdk",
    "https://drive.google.com/file/d/1kY1Gm0JYAaup3ag-Lss4VHzEJLdH01Oh/view?usp=drivesdk",
    "https://drive.google.com/file/d/1Gg-s5f6nW86obhYYJAnLn_Ct3V1Pgope/view?usp=drivesdk",
    "https://drive.google.com/file/d/1kY1Gm0JYAaup3ag-Lss4VHzEJLdH01Oh/view?usp=drivesdk",
    "https://drive.google.com/file/d/1Jl42rdFg7vSG1OfOAlpqG11HdOTXUZ1E/view?usp=drivesdk",
]

LARGURA = 1080
ALTURA = 1920
H_TOPO = 650
H_BAIXO = ALTURA - H_TOPO
H_FAIXA = 300
FPS = 30

PALETAS = [
    ((255, 255, 255), (40, 220, 40), (255, 200, 0)),
    ((255, 220, 0), (255, 100, 0), (220, 0, 0)),
    ((0, 255, 255), (255, 0, 255), (255, 255, 0)),
    ((255, 200, 0), (255, 255, 255), (200, 150, 0)),
    ((0, 200, 0), (255, 220, 0), (0, 100, 255)),
    ((255, 100, 200), (150, 0, 255), (255, 255, 255)),
    ((255, 150, 0), (150, 255, 0), (0, 200, 100)),
    ((255, 220, 0), (255, 255, 255), (255, 50, 50)),
    ((0, 150, 255), (0, 255, 255), (180, 0, 255)),
    ((255, 100, 150), (255, 150, 0), (255, 220, 0)),
]


class Progresso:
    def __init__(self, total=8):
        self.total = total
        self.passo = 0

    def avancar(self, mensagem="Processando"):
        self.passo = min(self.passo + 1, self.total)
        pct = int(self.passo * 100 / self.total)
        n = pct * 30 // 100
        sys.stdout.write(
            f"\r[{('█' * n) + ('░' * (30 - n))}] {pct}% - {mensagem:<25}"
        )
        sys.stdout.flush()

    def concluir(self):
        self.passo = self.total
        self.avancar_final()

    def avancar_final(self):
        sys.stdout.write("\r[" + "█" * 30 + "] 100% - Concluído                 \n")
        sys.stdout.flush()


def perguntar(texto, obrigatorio=False):
    while True:
        valor = input(texto).strip()
        if valor or not obrigatorio:
            return valor
        print("⚠️ Este campo é obrigatório.")


def executar(cmd, timeout=None):
    return subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def verificar_dependencias():
    faltam = [x for x in ("ffmpeg", "ffprobe") if not shutil.which(x)]
    if faltam:
        raise RuntimeError(
            "Instale as dependências no Termux: pkg install ffmpeg"
        )
    if not GEMINI_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY não configurada. Configure sua chave Gemini "
            "antes de executar."
        )


def limpar_temporarios():
    for p in TEMP.iterdir():
        try:
            if p.is_file() or p.is_symlink():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p)
        except OSError:
            pass


def normalizar_link_drive(url):
    if "drive.google.com" not in url:
        return url
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if not m:
        m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if not m:
        return url
    return f"https://drive.google.com/uc?export=download&id={m.group(1)}"


def baixar(url, prefixo):
    if not shutil.which("yt-dlp"):
        raise RuntimeError(
            "yt-dlp não encontrado. Instale com: pip install -U yt-dlp"
        )

    url = normalizar_link_drive(url)
    modelo = str(TEMP / f"{prefixo}.%(ext)s")

    r = subprocess.run(
        [
            "yt-dlp", "--no-playlist", "--force-overwrites",
            "--no-warnings", "--no-progress",
            "--merge-output-format", "mp4",
            "-o", modelo, url,
        ],
        capture_output=True,
        text=True,
    )

    candidatos = [
        p for p in TEMP.glob(f"{prefixo}.*")
        if p.is_file() and p.suffix.lower() in
        {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
    ]

    if r.returncode != 0 or not candidatos:
        destino = TEMP / f"{prefixo}.mp4"
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=90) as resposta:
                tipo = resposta.headers.get("Content-Type", "").lower()
                if "text/html" in tipo:
                    raise RuntimeError(
                        "O link retornou uma página HTML, não um vídeo."
                    )
                with open(destino, "wb") as arquivo:
                    shutil.copyfileobj(resposta, arquivo)
        except Exception as e:
            detalhe = (r.stderr or r.stdout or str(e))[-700:]
            raise RuntimeError(
                f"Não foi possível baixar {prefixo}: {detalhe}"
            ) from e
        candidatos = [destino]

    arquivo = max(candidatos, key=lambda p: p.stat().st_mtime)
    if arquivo.stat().st_size < 1024:
        raise RuntimeError(f"Arquivo de vídeo inválido: {arquivo.name}")
    return arquivo


def meta(url):
    try:
        r = subprocess.run(
            [
                "yt-dlp", "--no-playlist", "--dump-single-json",
                "--skip-download", "--no-warnings",
                normalizar_link_drive(url),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=40,
        )
        d = json.loads(r.stdout)
        return {
            "title": d.get("title", ""),
            "description": d.get("description", ""),
            "uploader": d.get("uploader") or d.get("channel") or "",
        }
    except Exception:
        return {"title": "", "description": "", "uploader": ""}


def info(caminho):
    r = executar([
        "ffprobe", "-v", "error", "-show_streams",
        "-show_format", "-of", "json", str(caminho),
    ], timeout=30)
    d = json.loads(r.stdout)
    dur = float(d.get("format", {}).get("duration", 0) or 0)
    video = next(
        (s for s in d.get("streams", []) if s.get("codec_type") == "video"),
        {},
    )
    tem_audio = any(
        s.get("codec_type") == "audio" for s in d.get("streams", [])
    )
    return dur, video.get("width", 0), video.get("height", 0), tem_audio


def extrair_frames(caminho, qtd=10):
    dur, _, _, _ = info(caminho)
    if dur <= 0:
        raise RuntimeError("Não consegui identificar a duração do vídeo.")

    frames = []
    for i in range(qtd):
        tempo = min(dur * (i + 1) / (qtd + 1), max(0, dur - 0.1))
        saida = TEMP / f"ia_{i + 1}.jpg"
        try:
            executar([
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", str(tempo), "-i", str(caminho),
                "-frames:v", "1", "-vf", "scale=512:-2",
                "-q:v", "5", str(saida),
            ], timeout=20)
            if saida.exists() and saida.stat().st_size:
                frames.append(
                    base64.b64encode(saida.read_bytes()).decode("ascii")
                )
        except Exception:
            continue

    return frames


def identificar_pessoas(frames):
    """
    Analisa os 10 frames com 4 modelos em PARALELO.
    Foco TOTAL em rostos/pessoas. Silencioso nos que falham.
    """
    if not frames:
        return "Não foi possível extrair imagens do vídeo."

    prompt = (
        "Você é um especialista em reconhecimento facial e visual.\n"
        "Olhe ATENTAMENTE os 10 frames abaixo (todos do MESMO vídeo, em "
        "momentos diferentes).\n\n"
        "SUA MISSÃO: IDENTIFICAR TODAS AS PESSOAS QUE APARECEM.\n\n"
        "Para CADA PESSOA visível, responda:\n"
        "- ROSTO: cor de pele, formato, cabelo (cor, comprimento, estilo), "
        "sobrancelha, barba/bigode, idade aparente\n"
        "- EXPRESSÃO: sorrindo, rindo, sério, surpreso, cantando\n"
        "- ACESSÓRIOS: boné, óculos, corrente, brinco, piercing, tatuagem\n"
        "- ROUPA: camisa, casaco, cores, uniforme, time, marca, logo\n"
        "- NOME: se reconhecer alguém famoso/influencer/jogador/cantor "
        "com CERTEZA (90%+), DIGA O NOME. Se não tiver certeza, escreva "
        "'não reconheci'. NUNCA invente.\n\n"
        "DEPOIS RESPONDA:\n"
        "- QUANTAS PESSOAS: número exato\n"
        "- QUEM É QUEM: se tiver 2+, diga quem tá na esquerda/direita/centro\n"
        "- O QUE FAZEM: ação de cada um (dançando, cantando, rindo, "
        "jogando bola, tocando instrumento)\n"
        "- CENÁRIO: onde estão (casa, rua, estádio, etc)\n"
        "- EMOÇÃO GERAL: qual o sentimento do vídeo\n\n"
        "Responda em português brasileiro, texto simples, sem JSON, "
        "sem markdown. Seja ESPECÍFICO e DESCRITIVO."
    )

    modelos_analise = [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
    ]

    resultados = {}

    def rodar(modelo):
        try:
            r = _chamar(prompt, GEMINI_KEY, modelo, imagens_b64=frames)
            return modelo, r
        except Exception:
            return modelo, None

    # Roda os 4 em paralelo (silencioso)
    with ThreadPoolExecutor(max_workers=4) as ex:
        tarefas = [ex.submit(rodar, m) for m in modelos_analise]
        for t in as_completed(tarefas):
            modelo, resp = t.result()
            if resp:
                resultados[modelo] = resp

    if not resultados:
        return "Nenhum modelo conseguiu analisar as imagens."

    bons = []
    for modelo, resp in resultados.items():
        bons.append(f"=== Analise por {modelo} ===\n{resp}")

    return "\n\n".join(bons)



def gerar_conteudo(identificacao, metadados):
    titulo_orig = (metadados.get("title") or "")[:250]
    descricao_orig = (metadados.get("description") or "")[:500]
    canal = (metadados.get("uploader") or "")[:100]

    prompt = f"""
Crie metadados para um YouTube Short de reação em português brasileiro.

REGRAS:
1) Use SOMENTE os nomes que aparecem na ANÁLISE VISUAL abaixo.
   Se a análise diz "não reconheci", use DESCRIÇÕES específicas:
   "o menino de boné", "o cara de corrente de ouro", "a dupla",
   "o pai e o filho", "o garoto jogando bola", etc.
2) NUNCA invente nomes de pessoas.
3) O TÍTULO deve terminar SEMPRE com " #Shorts" no final.
4) Mencione QUEM aparece (nome ou descrição) e O QUE FAZ no título.
5) Use os trends/hashtags virais do momento que você conhece (TikTok,
   Instagram, YouTube) para turbinar o alcance.

ANÁLISE VISUAL (4 modelos combinados):
{identificacao[:8000]}

TÍTULO ORIGINAL: {titulo_orig}
CANAL DE ORIGEM: {canal}
DESCRIÇÃO ORIGINAL: {descricao_orig}

Responda SOMENTE com JSON válido:
titulo: título atrativo, até 60 caracteres, terminando OBRIGATORIAMENTE com " #Shorts"
descricao: 3 a 4 linhas, terminando com pergunta pertinente
tags: 20 a 25 tags separadas por vírgula (palavras-chave virais, sem #)
hashtags: 15 a 20 hashtags separadas por espaço (incluindo #Shorts no final)
frase_curta: 1 a 4 palavras, em MAIÚSCULAS, sem emoji, para faixa visual

Exemplo de título: "Chris dançando passinho de time #Shorts"

Formato:
{{"titulo":"...","descricao":"...","tags":"...","hashtags":"...","frase_curta":"..."}}
"""

    resp = gemini_gerar(prompt, GEMINI_KEY)
    if not resp:
        raise RuntimeError("A IA não retornou conteúdo.")
    dados = extrair_json(resp)
    if not isinstance(dados, dict):
        raise RuntimeError("A IA não retornou JSON válido.")

    titulo = str(dados.get("titulo", "")).strip()
    descricao = str(dados.get("descricao", "")).strip()
    tags_str = str(dados.get("tags", "")).strip()
    hashtags = str(dados.get("hashtags", "")).strip()
    frase = str(dados.get("frase_curta", "REAÇÃO ÉPICA")).strip().upper()

    # FORCA #Shorts no final do titulo
    titulo = titulo.rstrip()
    if not titulo.lower().endswith("#shorts"):
        titulo = re.sub(r"\s*#shorts\s*", " ", titulo, flags=re.IGNORECASE).strip()
        titulo = titulo[:50].strip() + " #Shorts"
    if len(titulo) > 100:
        titulo = titulo[:97] + "..."

    # FORCA #Shorts no final das hashtags
    if not hashtags.lower().rstrip().endswith("#shorts"):
        hashtags = re.sub(r"\s*#shorts\s*", " ", hashtags, flags=re.IGNORECASE).strip()
        hashtags = hashtags + " #Shorts"

    # Adiciona hashtags virais se nao tiver
    virais = ["#viral", "#viralizou", "#trending", "#paravoce", "#fyp", "#foryou"]
    for v in virais:
        if v not in hashtags.lower():
            hashtags = hashtags + " " + v
            if len(hashtags.split()) >= 25:
                break

    # Processa tags
    tags_lista = [t.strip().lower() for t in tags_str.split(",") if t.strip()]
    vistas = set()
    tags_limpa = []
    for t in tags_lista:
        if t not in vistas:
            vistas.add(t)
            tags_limpa.append(t)

    for tv in ["viral", "shorts", "trending", "fyp", "paravoce", "viralizou"]:
        if tv not in vistas:
            tags_limpa.append(tv)
            vistas.add(tv)
            if len(tags_limpa) >= 30:
                break

    frase = re.sub(r"[^A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ0-9 ]", "", frase)
    frase = " ".join(frase.split())[:35] or "REAÇÃO ÉPICA"

    if not titulo:
        titulo = "Confira esta reação #Shorts"
    if not descricao:
        descricao = "O que você achou desse momento? Conte nos comentários."

    return titulo, descricao, hashtags, frase, tags_limpa



def obter_fonte():
    fonte = FONTES / "Anton-Regular.ttf"
    if fonte.exists() and fonte.stat().st_size > 10000:
        return fonte

    url = (
        "https://raw.githubusercontent.com/google/fonts/main/"
        "ofl/anton/Anton-Regular.ttf"
    )
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            dados = r.read()
        if len(dados) < 10000:
            raise RuntimeError("Fonte baixada incompleta.")
        fonte.write_bytes(dados)
        return fonte
    except Exception:
        for alternativa in (
            "/system/fonts/Roboto-Bold.ttf",
            "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        ):
            if Path(alternativa).exists():
                return Path(alternativa)
        raise RuntimeError(
            "Não consegui obter uma fonte. Verifique a internet."
        )


def desenhar_faixa(frase):
    img = Image.new("RGBA", (LARGURA, H_FAIXA), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fonte_path = obter_fonte()

    DOURADO = (255, 200, 0, 255)
    PRETO = (0, 0, 0, 255)

    cores_paleta = random.choice(PALETAS)

    palavras = frase.strip().upper().split()
    if not palavras:
        palavras = ["VIDEO", "INTERESSANTE"]

    if len(palavras) == 1:
        partes = [palavras[0]]
        cores = [cores_paleta[0]]
    elif len(palavras) == 2:
        partes = [palavras[0], palavras[1]]
        cores = [cores_paleta[0], cores_paleta[1]]
    else:
        meio = (len(palavras) + 1) // 2
        partes = [" ".join(palavras[:meio]), " ".join(palavras[meio:])]
        cores = [cores_paleta[0], cores_paleta[1]]

    def achar_tam(txt, max_tam):
        tam = max_tam
        while tam > 40:
            f = ImageFont.truetype(str(fonte_path), tam)
            b = draw.textbbox((0, 0), txt, font=f)
            if (b[2] - b[0]) <= LARGURA - 80:
                return tam
            tam -= 5
        return 40

    def desenhar(txt, y, cor, max_tam):
        if not txt:
            return y
        tam = achar_tam(txt, max_tam)
        fonte = ImageFont.truetype(str(fonte_path), tam)
        bbox = draw.textbbox((0, 0), txt, font=fonte)
        largura = bbox[2] - bbox[0]
        altura = bbox[3] - bbox[1]
        x = (LARGURA - largura) // 2

        for dx in range(-10, 11):
            for dy in range(-10, 11):
                if dx*dx + dy*dy <= 100:
                    draw.text((x+dx, y+dy), txt, font=fonte, fill=DOURADO)
        for dx in range(-5, 6):
            for dy in range(-5, 6):
                if dx*dx + dy*dy <= 25:
                    draw.text((x+dx, y+dy), txt, font=fonte, fill=PRETO)
        draw.text((x, y), txt, font=fonte, fill=cor + (255,) if len(cor) == 3 else cor)

        return y + altura + 12

    y = 15
    for i, (parte, cor) in enumerate(zip(partes, cores)):
        max_tam = 140 if i == 0 else 120
        y = desenhar(parte, y, cor, max_tam)

    saida = TEMP / "faixa.png"
    img.save(saida)
    return saida


def montar(video_topo, video_baixo, faixa_path):
    dur_baixo, _, _, audio_baixo = info(video_baixo)
    dur_topo, _, _, _ = info(video_topo)

    if dur_baixo <= 0:
        raise RuntimeError("O vídeo de reação está sem duração.")
    if dur_topo <= 0:
        raise RuntimeError("O vídeo do topo está sem duração.")

    faixa_y = ALTURA - H_FAIXA - 90

    filtro = (
        f"[0:v]setpts=PTS-STARTPTS,"
        f"scale={LARGURA}:{H_TOPO}:force_original_aspect_ratio=increase,"
        f"crop={LARGURA}:{H_TOPO},fps={FPS},setsar=1[top];"
        f"[1:v]setpts=PTS-STARTPTS,"
        f"scale={LARGURA}:{H_BAIXO}:force_original_aspect_ratio=increase,"
        f"crop={LARGURA}:{H_BAIXO},fps={FPS},setsar=1[baixo];"
        f"[top][baixo]vstack=inputs=2[base];"
        f"[2:v]format=rgba[faixa];"
        f"[base][faixa]overlay=x=0:y={faixa_y}:shortest=1,"
        f"format=yuv420p[outv]"
    )

    saida = TEMP / "final.mp4"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-stream_loop", "-1", "-i", str(video_topo),
        "-i", str(video_baixo),
        "-loop", "1", "-framerate", str(FPS), "-i", str(faixa_path),
        "-filter_complex", filtro,
        "-map", "[outv]",
    ]

    if audio_baixo:
        cmd += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]

    cmd += [
        "-t", f"{dur_baixo:.3f}",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-crf", "24", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(saida),
    ]

    try:
        executar(cmd, timeout=max(180, int(dur_baixo * 12)))
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            "A montagem demorou demais. Tente um vídeo mais curto."
        ) from e

    if not saida.exists() or saida.stat().st_size < 10000:
        raise RuntimeError("O FFmpeg não criou um vídeo final válido.")

    dur_final, largura, altura, _ = info(saida)
    if largura != LARGURA or altura != ALTURA:
        raise RuntimeError("O vídeo final não está em 1080x1920.")
    if dur_final <= 0:
        raise RuntimeError("Não foi possível validar o vídeo final.")

    return saida


def salvar_publicacao(dados):
    temporario = PUBLICACAO.with_suffix(".tmp")
    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporario.replace(PUBLICACAO)


def main():
    verificar_dependencias()
    limpar_temporarios()

    progresso = Progresso()
    url_topo = random.choice(LINKS_TOPO)

    print("🎬 CRIADOR DE SHORTS — REAÇÃO")
    print("Use vídeos próprios ou cujo uso você tenha autorização.")
    url_baixo = perguntar("\n🔽 Link do vídeo de reação: ", True)

    progresso.avancar("Baixando vídeo do topo")
    video_topo = baixar(url_topo, "topo")

    progresso.avancar("Baixando reação")
    video_baixo = baixar(url_baixo, "baixo")

    progresso.avancar("Extraindo 10 frames")
    frames = extrair_frames(video_baixo, qtd=10)

    progresso.avancar("Lendo metadados")
    metadados = meta(url_baixo)

    progresso.avancar("Analisando rostos")
    identificacao = identificar_pessoas(frames)

    progresso.avancar("Gerando título e hashtags")
    titulo, descricao, hashtags, frase, tags_ia = gerar_conteudo(
        identificacao, metadados
    )

    progresso.avancar("Criando faixa")
    faixa = desenhar_faixa(frase)

    progresso.avancar("Montando e validando vídeo")
    video_final = montar(video_topo, video_baixo, faixa)

    progresso.concluir()

    data = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = Path("/sdcard/Download") / f"criar_{data}.mp4"
    try:
        if Path("/sdcard/Download").exists():
            shutil.copy2(video_final, dest)
            print(f"\n📱 Cópia salva em: {dest}")
        else:
            print("\n⚠️ Pasta Download não encontrada.")
            print("Execute termux-setup-storage e aceite a permissão.")
    except Exception as e:
        print(f"\n⚠️ Não foi possível copiar para Downloads: {e}")

    try:
        tags_local = pegar_tags(20) or []
    except Exception:
        tags_local = []

    tags_final = []
    vistas = set()
    for t in (tags_ia or []) + (tags_local or []):
        t_limpo = str(t).strip().lower()
        if t_limpo and t_limpo not in vistas:
            vistas.add(t_limpo)
            tags_final.append(t_limpo)
    tags = tags_final[:30]

    dados = {
        "video": str(video_final),
        "url_topo": url_topo,
        "url_baixo": url_baixo,
        "titulo": titulo,
        "descricao": descricao,
        "tags": tags,
        "hashtags": hashtags,
        "frase_curta": frase,
        "privacidade": "public",
    }
    salvar_publicacao(dados)

    print("\n" + "=" * 45)
    print("RESULTADO")
    print("=" * 45)
    print(f"\n🎬 TÍTULO:\n{titulo}")
    print(f"\n📝 DESCRIÇÃO:\n{descricao}")
    print(f"\n🏷️ TAGS:\n{', '.join(map(str, tags))}")
    print(f"\n#️⃣ HASHTAGS:\n{hashtags}")
    print(f"\n💬 FRASE:\n{frase}")
    print(f"\n🎥 VÍDEO:\n{video_final}")
    print(f"\n📦 TAMANHO: {video_final.stat().st_size / 1024 / 1024:.1f} MB")

    if perguntar("\n🚀 Enviar para o YouTube agora? (s/n): ").lower() == "s":
        enviar = BASE / "enviar_short.py"
        if not enviar.exists():
            print(f"❌ Arquivo não encontrado: {enviar}")
            print("O vídeo está montado e os dados foram salvos.")
            return
        subprocess.run([sys.executable, str(enviar)], check=False)
    else:
        print("\n⏸️ Salvo. Quando quiser, execute:")
        print("python ~/yt/enviar_short.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado pelo usuário.")
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        sys.exit(1)
