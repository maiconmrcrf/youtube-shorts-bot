"""
enviar_short.py — Posta o vídeo do publicacao.json no YouTube.
- NÃO pergunta nada (modo automático).
- Se postar: sai com código 0.
- Se falhar por limite: sai com código 1 (o loop tenta de novo).
"""
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
PUBLICACAO = BASE / "publicacao.json"


def log(msg):
    print(msg, flush=True)


def main():
    if not PUBLICACAO.exists():
        log("❌ publicacao.json não encontrado.")
        log("   Rode criar.py primeiro.")
        return 2

    try:
        dados = json.loads(PUBLICACAO.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"❌ Erro lendo publicacao.json: {e}")
        return 2

    video = dados.get("video", "")
    titulo = dados.get("titulo", "")
    descricao = dados.get("descricao", "")
    tags = dados.get("tags", [])
    hashtags = dados.get("hashtags", "")
    privacidade = dados.get("privacidade", "public")

    if not video or not Path(video).exists():
        log(f"❌ Vídeo não encontrado: {video}")
        return 2

    # Junta descrição + hashtags
    desc_final = descricao.strip()
    if hashtags:
        desc_final += "\n\n" + hashtags

    log("=" * 60)
    log("  📤 ENVIANDO SHORT")
    log("=" * 60)
    log(f"  🎬 Título: {titulo}")
    log(f"  📁 Vídeo: {video}")
    log(f"  🔒 Privacidade: {privacidade}")
    log("")

    # Importa as libs do YouTube só agora (pra falhar rápido se faltar)
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as e:
        log(f"❌ Faltando biblioteca: {e}")
        log("   Rode: pip install google-auth google-auth-oauthlib google-api-python-client")
        return 2

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
    TOKEN = BASE / "token.json"
    CREDS = BASE / "client_secrets.json"

    creds = None
    if TOKEN.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds:
            if not CREDS.exists():
                log(f"❌ client_secrets.json não encontrado em {CREDS}")
                return 2
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": titulo[:100],
            "description": desc_final[:5000],
            "tags": tags[:500],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": privacidade,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 4,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    log("  ⏳ Enviando...")
    response = None
    erro_final = None
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                log(f"     {pct}%")
        except Exception as e:
            erro_final = e
            break

    if erro_final:
        msg = str(erro_final)
        log("")
        log("=" * 60)
        # Detecta limite de cota
        if "quotaExceeded" in msg or "uploadLimitExceeded" in msg or "429" in msg or "403" in msg:
            log("  ⏳ LIMITE DIÁRIO DO YOUTUBE ATINGIDO")
            log("  👉 Vou tentar de novo daqui a pouco.")
            log("=" * 60)
            return 1  # sinaliza pro loop: falhou, tenta de novo
        else:
            log(f"  ❌ ERRO: {msg}")
            log("=" * 60)
            return 1

    if response:
        vid = response.get("id", "?")
        log("")
        log("=" * 60)
        log(f"  ✅ POSTADO! https://youtu.be/{vid}")
        log("=" * 60)
        # Remove publicacao.json pra não repostar o mesmo
        try:
            PUBLICACAO.unlink()
            log("  🗑️  publicacao.json removido.")
        except Exception:
            pass
        return 0

    log("❌ Sem resposta da API.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\nCancelado.")
        sys.exit(2)
    except Exception as e:
        log(f"❌ Erro fatal: {e}")
        sys.exit(2)
