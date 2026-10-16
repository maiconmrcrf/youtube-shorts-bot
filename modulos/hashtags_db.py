# ============================================================
# BANCO GLOBAL DE HASHTAGS
# O robô escolhe as mais relevantes pra cada vídeo
# ============================================================

HASHTAGS_GLOBAIS = {
    "viral": [
        "#Viral", "#Viralizou", "#Viralizando", "#Bombando", "#Hype",
        "#Trending", "#Trend", "#Tendência", "#Explodiu", "#Bomba",
        "#Sucesso", "#Hit", "#Fenômeno", "#Top", "#Top1",
    ],
    "engajamento": [
        "#Like", "#Curte", "#Comenta", "#Compartilha", "#Salva",
        "#InscrevaSe", "#Seguir", "#Segue", "#Favorita", "#Amei",
        "#TopDosTop", "#Inscrição", "#AtivaOSino", "#Sininho", "#Notificação",
    ],
    "brasil": [
        "#Brasil", "#Brasileiro", "#BR", "#BrasilSil", "#BrasilUrgente",
        "#SãoPaulo", "#RioDeJaneiro", "#Nordeste", "#Sul", "#Carioca",
        "#Paulista", "#Mineiro", "#Gaúcho", "#Baiano", "#Brasileirissimo",
    ],
    "shorts": [
        "#Shorts", "#Short", "#ShortsBrasil", "#ShortsViral", "#Shorts2026",
        "#YouTubeShorts", "#ShortsFeed", "#ShortsDaily", "#ReelsBrasil", "#FYP",
        "#ParaVocê", "#ForYou", "#ParaVoce", "#Explorar", "#Descobrir",
    ],
    "curiosidade": [
        "#Curiosidade", "#Curiosidades", "#VocêSabia", "#SabiaDisso",
        "#Fatos", "#Fato", "#Descobri", "#Descoberta", "#Segredo",
        "#Mistério", "#Revelação", "#Surpreendente", "#Inacreditável", "#Chocante", "#Impressionante",
    ],
    "emoção": [
        "#Emocionante", "#Inspirador", "#Motivação", "#Reflexão", "#Superação",
        "#Força", "#Fé", "#Gratidão", "#Amor", "#Esperança",
        "#Surreal", "#Impactante", "#Marcante", "#Profundo", "#Verdade",
    ],
    "humor": [
        "#Humor", "#Comédia", "#Piada", "#Risada", "#Meme",
        "#Zoeira", "#Kkkk", "#Engraçado", "#Rir", "#Hilário",
        "#VídeoEngraçado", "#Trollagem", "#Palhaçada", "#Sátira", "#HumorBrasil",
    ],
    "estilo_vida": [
        "#Lifestyle", "#VidaReal", "#Rotina", "#DiaADia", "#Vlog",
        "#Motivacional", "#Sucesso", "#Foco", "#Meta", "#Objetivo",
        "#Sonho", "#Vencer", "#Vitória", "#Conquista", "#Realização",
    ],
    "gerais": [
        "#Vídeo", "#Vídeos", "#Assista", "#Assistir", "#Imperdível",
        "#Melhor", "#Incrível", "#Top", "#Épico", "#Lendário",
        "#Único", "#Exclusivo", "#Raro", "#Novidade", "#Lançamento",
        "#Atual", "#Hoje", "#Agora", "#Recente", "#Novo",
    ],
}

# Tags do YouTube (campo separado, sem #)
TAGS_GLOBAIS = [
    "shorts", "viral", "viralizou", "brasil", "youtube shorts",
    "video viral", "melhores shorts", "shorts brasil", "trending",
    "curiosidades", "fatos", "você sabia", "top", "imperdível",
    "conteúdo viral", "melhores vídeos", "vídeo do dia", "bombando",
    "assista agora", "não perca", "incrível", "surpreendente",
]


def pegar_hashtags(qtd=30, categorias=None):
    """Retorna hashtags globais variadas."""
    import random

    if categorias is None:
        categorias = list(HASHTAGS_GLOBAIS.keys())

    pool = []
    for cat in categorias:
        pool += HASHTAGS_GLOBAIS.get(cat, [])

    # Remove duplicadas
    vistas = set()
    unicas = []
    for h in pool:
        if h.lower() not in vistas:
            vistas.add(h.lower())
            unicas.append(h)

    qtd = min(qtd, len(unicas))
    return random.sample(unicas, qtd)


def pegar_tags(qtd=20):
    """Retorna tags globais variadas."""
    import random
    qtd = min(qtd, len(TAGS_GLOBAIS))
    return random.sample(TAGS_GLOBAIS, qtd)
