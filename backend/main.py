from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import feedparser
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import time
import urllib.parse
import requests

app = FastAPI()

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# FRONTEND (static)
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

from starlette.staticfiles import StaticFiles

class TunedStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "no-store"
        else:
            response.headers["Cache-Control"] = "public, max-age=3600"
        return response

app.mount("/static", TunedStaticFiles(directory=FRONTEND_DIR), name="static")


def frontend_file(filename: str):
    response = FileResponse(os.path.join(FRONTEND_DIR, filename))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def serve_index():
    return frontend_file("index.html")

@app.get("/fpm")
def serve_fpm():
    return frontend_file("fpm.html")

@app.get("/sobre")
def serve_sobre():
    return frontend_file("sobre.html")

@app.get("/escritorio")
def serve_escritorio():
    return frontend_file("escritorio.html")

# =========================
# CONFIG
# =========================
MIN_RELEVANCIA = 2
TZ_BRASIL = timezone(timedelta(hours=-3))
REQUEST_TIMEOUT_SECONDS = 8
FEED_CACHE_TTL_SECONDS = 600
RESULT_CACHE_TTL_SECONDS = 300
MAX_FEED_WORKERS = 6
USER_AGENT = "RadarNoticias/1.0 (+https://local.app)"

_feed_cache = {}
_result_cache = {}

# =========================
# PUBLISHERS
# =========================
ROYALTIES_PUBLISHERS = [
    "Valor Econômico","Reuters","Agência Brasil","g1","Estadão","Folha",
    "O Globo","CNN Brasil","InfoMoney","Petrobras","ANP",
    "Agência Nacional do Petróleo","IBAMA","Portos e Navios",
    "Brasil Energia","Offshore Energy","BNAmericas","Eixos","epbr",
]

FPM_PUBLISHERS = [
    # originais
    "Agência Brasil","g1","Estadão","Folha","O Globo","UOL",
    "CNN Brasil","InfoMoney","Valor Econômico","Consultor Jurídico",
    "ConJur","CNM","Confederação Nacional de Municípios",
    "IBGE","STF","STJ","TCU","Agência Senado",
    "Câmara dos Deputados","Senado",

    # fortalecimento institucional
    "Portal da Transparência",
    "Ministério da Fazenda",
    "Ministério do Planejamento",
    "Tesouro Nacional",
    "Secretaria do Tesouro Nacional",
    "Gov.br",
    "Planalto",
    "Diário Oficial da União",
    "Diário Oficial",
    "Tribunal de Contas da União",
    "Tribunal de Contas",
    "CNM Notícias",
    "Agência Câmara",
    "Agência Senado Notícias",
]

ESCRITORIO_PUBLISHERS = [
    # Grandes portais
    "g1","UOL","Estadão","Folha","O Globo","CNN Brasil",
    "Valor Econômico","InfoMoney","Agência Brasil","O TEMPO",

    # Jurídicos
    "Consultor Jurídico","ConJur","Migalhas",
    "JOTA","Justiça em Foco","Rota Jurídica",
    "JusBrasil","Tribunal de Justiça",
    "STF","STJ","TRF","TJ",

    # Governamentais
    "Diário Oficial","Diário Oficial da União",
    "Gov.br","Planalto",

    # Redes sociais
    "Instagram","LinkedIn","Facebook",
    "X","Twitter","YouTube",
    "Threads","TikTok",

    # Busca ampla
    "Google","Bing News"
]

# =========================
# TERMOS (ORIGINAIS COMPLETOS)
# =========================
ROYALTIES_TERMS = [
    "royalties","royalties de petróleo","royalties do petróleo",
    "royalties gás natural","royalties de gás natural",
    "participação especial","compensação financeira",
    "anp","agência nacional do petróleo","gás natural",
    "exploração de petróleo","exploração de gás natural",
    "processo judicial anp","processo judicial royalties de petróleo",
    "processo judicial royalties gás natural","exploração","produção",
    "perfuração","poço","poço exploratório","sísmica",
    "levantamento sísmico","bloco exploratório","oferta permanente",
    "leilão anp","rodada anp","contrato de concessão",
    "contrato de partilha","campo","campo produtor",
    "entrada em produção","ramp-up","offshore","onshore",
    "plataforma","plataforma de petróleo","fpso","navio-plataforma",
    "sonda","sonda de perfuração","gasoduto","oleoduto",
    "terminal marítimo","escoamento de produção","pré-sal","presal",
    "margem equatorial","bacia da foz do amazonas",
    "bacia de campos","bacia de santos","bacia potiguar",
    "bacia de sergipe-alagoas","bacia do recôncavo",
    "bacia do parnaíba","municípios confrontantes",
    "redistribuição de royalties","lei dos royalties",
    "ação judicial","stf","stj","tcu","vazamento de óleo",
    "derramamento de óleo","incidente em plataforma",
    "paralisação de produção",
]

FPM_TERMS = [
    # termos originais
    "fpm","fundo de participação dos municipios",
    "fundo de participação dos municípios",
    "fundo de participação municipal","ibge","censo",
    "processo judicial fpm","majoração do coeficiente",
    "coeficiente do fpm","coeficiente fpm",
    "coeficiente populacional","repasse fpm",
    "transferência constitucional","revisão do coeficiente",

    # fortalecimento institucional
    "transferências constitucionais",
    "transferência intergovernamental",
    "receita municipal",
    "receitas municipais",
    "arrecadação municipal",
    "finanças municipais",
    "orçamento municipal",
    "orçamento dos municípios",
    "partilha de recursos",
    "redistribuição do fpm",
    "quota do fpm",
    "quota-parte do fpm",

    # IBGE e dados demográficos
    "estimativa populacional",
    "população estimada",
    "dados do ibge",
    "divulgação do censo",
    "revisão populacional",
    "atualização populacional",
    "contagem populacional",
    "projeção populacional",

    # jurídico
    "ação no stf sobre fpm",
    "ação no stj sobre fpm",
    "decisão judicial fpm",
    "liminar fpm",
    "mandado de segurança fpm",
    "controle de constitucionalidade fpm",
    "artigo 159 da constituição",
    "constituição federal art 159",
    "tribunal de contas da união fpm",
    "tcu fpm",

    # CNM / municipalismo
    "confederação nacional de municípios",
    "cnm fpm",
    "movimento municipalista",
    "municipalismo",
    "prefeituras",
    "prefeitos",
    "impacto do fpm",
    "queda do fpm",
    "aumento do fpm",

    # economia pública
    "receita corrente líquida",
    "equilíbrio fiscal municipal",
    "responsabilidade fiscal municípios",
    "lei de responsabilidade fiscal",
    "impacto orçamentário fpm",

    # político-institucional
    "câmara dos deputados fpm",
    "senado fpm",
    "comissão de finanças e tributação",
    "reforma tributária municípios",
    "pacto federativo",
]

ESCRITORIO_TERMS = [
    "camilarodrigues.advogados",
    "camila rodrigues advogados",
    "camila rodrigues assessoria jurídica",
    "camila rodrigues advogada",
    "camila rodrigues assessoria jurídica",
    "camila rodrigues da silva",
    "camila rodrigues da silva sociedade individual de advocacia",
    "cr assessoria jurídica",
    "camila rodrigues escritório",
    "processo camila rodrigues",
    "ação camila rodrigues",
    "decisão camila rodrigues",
    "publicação camila rodrigues",
    "sociedade individual de advocacia",
    "prefeitura municipal",
    "prefeituras municipais",
    "município",
    "municípios",
    "administração pública municipal",
    "contrata advocacia",
    "contratação de advocacia",
    "contratação de escritório de advocacia",
    "escritório de advocacia especializado",
    "contrato de inexigibilidade",
    "inexigibilidade de licitação",
    "honorários de êxito",
    "recuperação de receitas",
    "recuperação de receitas públicas",
    "recuperação e revisão de receita pública",
    "revisão de receitas públicas",
    "receita pública",
    "receitas públicas",
    "ações judiciais e administrativas",
    "repasses constitucionais compulsórios",
    "transferências constitucionais",
    "fundo de participação dos municípios",
    "fundo de participacao dos municipios",
    "fpm",
    "receitas do fpm",
    "repasses do fpm",
    "revisão de repasses federais",
    "repasses federais",
]

# =========================
# FUNÇÕES DE BUSCA
# =========================
def preparar_lista(lista):
    return tuple(item.lower() for item in lista)

ROYALTIES_TERMS_INDEX = preparar_lista(ROYALTIES_TERMS)
FPM_TERMS_INDEX = preparar_lista(FPM_TERMS)
ESCRITORIO_TERMS_INDEX = preparar_lista(ESCRITORIO_TERMS)

ROYALTIES_PUBLISHERS_INDEX = preparar_lista(ROYALTIES_PUBLISHERS)
FPM_PUBLISHERS_INDEX = preparar_lista(FPM_PUBLISHERS)
ESCRITORIO_PUBLISHERS_INDEX = preparar_lista(ESCRITORIO_PUBLISHERS)

def calcular_relevancia(texto: str, termos) -> int:
    t = (texto or "").lower()
    score = 0
    for termo in termos:
        if termo in t:
            score += 1
    return score

def get_publisher(entry) -> str:
    title = getattr(entry, "title", "") or ""
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return ""

def publisher_valido(publisher: str, lista) -> bool:
    if not publisher:
        return False
    p = publisher.lower()
    return any(item in p for item in lista)

def janela_datas(dias: int):
    agora = datetime.now(TZ_BRASIL)
    if dias == 1:
        inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        fim = agora.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        inicio = agora - timedelta(days=dias)
        fim = agora
    return inicio, fim

def normalizar_link(link: str) -> str:
    parsed = urllib.parse.urlparse(link or "")
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

def parse_feed_cached(url: str):
    agora = time.monotonic()
    cached = _feed_cache.get(url)
    if cached and agora - cached["created_at"] < FEED_CACHE_TTL_SECONDS:
        return cached["feed"]

    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except requests.RequestException:
        feed = feedparser.parse(b"")

    _feed_cache[url] = {"created_at": agora, "feed": feed}
    return feed

def parse_feeds_parallel(urls):
    if not urls:
        return []

    feeds = []
    max_workers = min(MAX_FEED_WORKERS, len(urls))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(parse_feed_cached, url): url for url in urls}
        for future in as_completed(future_map):
            feeds.append(future.result())
    return feeds

def finalizar_resultados(resultados):
    resultados.sort(key=lambda x: (x["relevancia"], x["data_sort"]), reverse=True)
    for item in resultados:
        item.pop("data_sort", None)
    return resultados

def resultado_cache_get(chave):
    cached = _result_cache.get(chave)
    agora = time.monotonic()
    if cached and agora - cached["created_at"] < RESULT_CACHE_TTL_SECONDS:
        return cached["payload"]
    return None

def resultado_cache_set(chave, payload):
    _result_cache[chave] = {"created_at": time.monotonic(), "payload": payload}
    return payload

def montar_payload(tipo, dias, metodo, resultados):
    return {
        "tipo": tipo,
        "periodo": "Hoje" if dias == 1 else f"Últimos {dias} dias",
        "metodo": metodo.capitalize(),
        "quantidade": len(resultados),
        "noticias": resultados,
    }

# =========================
# MÉTODO GOOGLE (ORIGINAL)
# =========================
def buscar_google(dias, termos, publishers, queries):
    inicio, fim = janela_datas(dias)
    resultados = []
    vistos = set()
    urls = []

    for q in queries:
        query = urllib.parse.quote(q)
        urls.append(
            "https://news.google.com/rss/search?"
            f"q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        )

    for feed in parse_feeds_parallel(urls):

        for entry in feed.entries:
            if not entry.get("published_parsed"):
                continue

            data_utc = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            data_pub = data_utc.astimezone(TZ_BRASIL)

            if not (inicio <= data_pub <= fim):
                continue

            link = getattr(entry, "link", "") or ""
            link_limpo = normalizar_link(link)
            if not link_limpo or link_limpo in vistos:
                continue
            vistos.add(link_limpo)

            publisher = get_publisher(entry)
            if not publisher_valido(publisher, publishers):
                continue

            texto = f"{getattr(entry,'title','')} {getattr(entry,'summary','')}"
            relev = calcular_relevancia(texto, termos)
            if relev < MIN_RELEVANCIA:
                continue

            resultados.append({
                "titulo": getattr(entry, "title", ""),
                "link": link,
                "data": data_pub.strftime("%d/%m/%Y"),
                "data_sort": data_pub,
                "fonte": publisher,
                "relevancia": relev
            })

    return finalizar_resultados(resultados)

# =========================
# RSS DIRETO
# =========================
RSS_FEEDS_ROYALTIES = [
    "https://g1.globo.com/rss/g1/economia/",
    "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml",
    "https://www.infomoney.com.br/feed/",
]

RSS_FEEDS_FPM = [
    "https://agenciabrasil.ebc.com.br/rss/politica/feed.xml",
    "https://www.cnm.org.br/rss",
]

def buscar_rss(dias, termos, publishers, feeds):
    inicio, fim = janela_datas(dias)
    resultados = []
    vistos = set()

    for feed in parse_feeds_parallel(feeds):

        for entry in feed.entries:
            if not entry.get("published_parsed"):
                continue

            data_utc = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            data_pub = data_utc.astimezone(TZ_BRASIL)

            if not (inicio <= data_pub <= fim):
                continue

            link = getattr(entry, "link", "") or ""
            link_limpo = normalizar_link(link)
            if not link_limpo or link_limpo in vistos:
                continue
            vistos.add(link_limpo)

            publisher = feed.feed.get("title", "RSS")
            if not publisher_valido(publisher, publishers):
                continue

            texto = f"{getattr(entry,'title','')} {getattr(entry,'summary','')}"
            relev = calcular_relevancia(texto, termos)
            if relev < MIN_RELEVANCIA:
                continue

            resultados.append({
                "titulo": getattr(entry, "title", ""),
                "link": link,
                "data": data_pub.strftime("%d/%m/%Y"),
                "data_sort": data_pub,
                "fonte": publisher,
                "relevancia": relev
            })

    return finalizar_resultados(resultados)

# =========================
# BING
# =========================

def buscar_bing(dias, termos, publishers, queries):
    inicio, fim = janela_datas(dias)
    resultados = []
    vistos = set()
    urls = []

    for q in queries:
        query = urllib.parse.quote(q)
        urls.append(f"https://www.bing.com/news/search?q={query}&format=rss")

    for feed in parse_feeds_parallel(urls):

        for entry in feed.entries:
            if not entry.get("published_parsed"):
                continue

            data_utc = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            data_pub = data_utc.astimezone(TZ_BRASIL)

            if not (inicio <= data_pub <= fim):
                continue

            link_original = getattr(entry, "link", "") or ""
            if not link_original:
                continue

            link_limpo = normalizar_link(link_original)

            if link_limpo in vistos:
                continue
            vistos.add(link_limpo)

            publisher = "Bing News"

            texto = f"{getattr(entry,'title','')} {getattr(entry,'summary','')}"
            relev = calcular_relevancia(texto, termos)
            if relev < MIN_RELEVANCIA:
                continue

            resultados.append({
                "titulo": getattr(entry, "title", ""),
                "link": link_original,  # mantém link original para o usuário
                "data": data_pub.strftime("%d/%m/%Y"),
                "data_sort": data_pub,
                "fonte": publisher,
                "relevancia": relev
            })

    return finalizar_resultados(resultados)

# =========================
# ENDPOINTS
# =========================
@app.get("/buscar-royalties")
def buscar_royalties(
    dias: int = Query(7, ge=1, le=60),
    metodo: str = Query("google")
):
    metodo = metodo.lower()
    chave_cache = ("royalties", dias, metodo)
    cached = resultado_cache_get(chave_cache)
    if cached:
        return cached

    queries = [
        "royalties de petróleo Brasil",
        "royalties gás natural Brasil",
        "ANP royalties",
        "Agência Nacional do Petróleo royalties",
        "exploração de petróleo Brasil",
        "exploração de gás natural Brasil",
        "processo judicial ANP",
        "processo judicial royalties de petróleo",
        "processo judicial royalties gás natural",
        "participação especial petróleo municípios",
        "margem equatorial petróleo",
        "bacia da foz do amazonas petróleo",
        "produção de petróleo offshore Brasil",
        "oferta permanente ANP blocos",
        "leilão ANP petróleo gás",
    ]

    if metodo == "rss":
        resultados = buscar_rss(dias, ROYALTIES_TERMS_INDEX, ROYALTIES_PUBLISHERS_INDEX, RSS_FEEDS_ROYALTIES)
    elif metodo == "bing":
        resultados = buscar_bing(dias, ROYALTIES_TERMS_INDEX, ROYALTIES_PUBLISHERS_INDEX, queries)
    else:
        resultados = buscar_google(dias, ROYALTIES_TERMS_INDEX, ROYALTIES_PUBLISHERS_INDEX, queries)

    payload = montar_payload("Royalties de Petróleo", dias, metodo, resultados)
    return resultado_cache_set(chave_cache, payload)

@app.get("/buscar-fpm")
def buscar_fpm(
    dias: int = Query(7, ge=1, le=60),
    metodo: str = Query("google")
):
    metodo = metodo.lower()
    chave_cache = ("fpm", dias, metodo)
    cached = resultado_cache_get(chave_cache)
    if cached:
        return cached

    queries = [
       # base direta
    "FPM",
    "Fundo de Participação dos Municípios",
    "Fundo de participação municipal",

    # repasses
    "repasse do FPM",
    "repasse FPM municípios",
    "repasse federal municípios",
    "transferência do FPM",
    "transferências constitucionais municípios",
    "Tesouro Nacional FPM",
    "Secretaria do Tesouro Nacional FPM",

    # linguagem jornalística
    "municípios recebem FPM",
    "prefeituras recebem FPM",
    "queda do FPM",
    "aumento do FPM",
    "valor do FPM",
    "terceiro decêndio do FPM",
    "segundo decêndio do FPM",
    "primeiro decêndio do FPM",

    # IBGE e coeficiente
    "coeficiente do FPM IBGE",
    "revisão coeficiente FPM",
    "estimativa populacional IBGE municípios",
    "censo IBGE impacto FPM",
    "majoração coeficiente FPM",

    # legislativo e judicial
    "projeto de lei FPM",
    "STF FPM decisão",
    "STJ FPM decisão",
    "TCU FPM",
    "ação judicial FPM",

    # contexto econômico
    "orçamento municipal FPM",
    "arrecadação municipal FPM",
    "receita municipal FPM",
    "impacto do FPM nos municípios",

    # pacto federativo
    "pacto federativo municípios",
    "reforma tributária municípios FPM",
    ]

    if metodo == "rss":
        resultados = buscar_rss(dias, FPM_TERMS_INDEX, FPM_PUBLISHERS_INDEX, RSS_FEEDS_FPM)
    elif metodo == "bing":
        resultados = buscar_bing(dias, FPM_TERMS_INDEX, FPM_PUBLISHERS_INDEX, queries)
    else:
        resultados = buscar_google(dias, FPM_TERMS_INDEX, FPM_PUBLISHERS_INDEX, queries)

    payload = montar_payload("FPM", dias, metodo, resultados)
    return resultado_cache_set(chave_cache, payload)

@app.get("/buscar-escritorio")
def buscar_escritorio(
    dias: int = Query(7, ge=1, le=365),
    metodo: str = Query("google")
):
    metodo = metodo.lower()
    chave_cache = ("escritorio", dias, metodo)
    cached = resultado_cache_get(chave_cache)
    if cached:
        return cached

    queries = [
        '"camilarodrigues.advogados"',
        '"Camila Rodrigues Advogados"',
        '"Camila Rodrigues Assessoria Jurídica"',
        '"Camila Rodrigues" advogada',
        '"Camila Rodrigues" assessoria jurídica',
        '"Camila Rodrigues da Silva" advocacia',
        '"Camila Rodrigues da Silva" "Sociedade Individual de Advocacia"',

        # variações estratégicas
        '"CR Assessoria Jurídica"',
        '"Camila Rodrigues" processo',
        '"Camila Rodrigues" decisão judicial',
        '"Camila Rodrigues" tribunal',
        '"Camila Rodrigues" Diário Oficial',
        '"Camila Rodrigues" publicação',
        '"Camila Rodrigues" "Fundo de Participação dos Municípios"',
        '"Camila Rodrigues" FPM',
        '"Camila Rodrigues" "recuperação de receitas"',
        '"Camila Rodrigues" "revisão de receitas"',
        '"Camila Rodrigues" "repasses constitucionais"',
        '"Camila Rodrigues" prefeitura',
        '"Camila Rodrigues" município',
        '"Camila Rodrigues" "prefeitura municipal"',
        '"Camila Rodrigues" "contratação de escritório de advocacia"',
        '"prefeitura municipal" "Camila Rodrigues" FPM',
        '"prefeitura municipal" advocacia FPM',
        '"prefeitura municipal" "recuperação de receitas"',
        '"município" "recuperação de receitas" FPM',
        '"advocacia" "recuperação de receitas" FPM',
        '"honorários de êxito" "Camila Rodrigues"',
        '"inexigibilidade" "Camila Rodrigues"',
        'site:otempo.com.br "Camila Rodrigues" FPM',
        'site:otempo.com.br "prefeitura municipal" advocacia',
        'site:otempo.com.br "recuperação de receitas" FPM',

        # redes sociais
        'site:instagram.com "Camila Rodrigues"',
        'site:linkedin.com "Camila Rodrigues"',
        'site:facebook.com "Camila Rodrigues"',
        'site:twitter.com "Camila Rodrigues"',
        'site:youtube.com "Camila Rodrigues"',
    ]

    if metodo == "rss":
        resultados = buscar_rss(dias, ESCRITORIO_TERMS_INDEX, ESCRITORIO_PUBLISHERS_INDEX, RSS_FEEDS_ROYALTIES)
    elif metodo == "bing":
        resultados = buscar_bing(dias, ESCRITORIO_TERMS_INDEX, ESCRITORIO_PUBLISHERS_INDEX, queries)
    else:
        resultados = buscar_google(dias, ESCRITORIO_TERMS_INDEX, ESCRITORIO_PUBLISHERS_INDEX, queries)

    return resultado_cache_set(
        chave_cache,
        montar_payload("Camila Rodrigues Assessoria Jurídica", dias, metodo, resultados),
    )
