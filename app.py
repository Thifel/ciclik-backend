from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse
import certifi
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# -------- Sessão HTTP robusta ----------
def make_session():
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    sess.verify = certifi.where()

    retry = Retry(
        total=5, connect=5, read=3, backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"GET", "POST"},
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)

    proxy_url = os.getenv("SEFAZ_PROXY_URL")
    if proxy_url:
        sess.proxies.update({"https": proxy_url, "http": proxy_url})

    return sess

# -------- Força HTTPS --------
def force_https_if_sefaz_ba(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.netloc.lower() == "nfe.sefaz.ba.gov.br" and parsed.scheme != "https":
            parsed = parsed._replace(scheme="https")
            return urlunparse(parsed)
    except Exception:
        pass
    return url

# -------- Núcleo de extração ----------
def extrair_produtos(qr_url):
    session = make_session()
    produtos = []
    try:
        qr_url = force_https_if_sefaz_ba(qr_url)

        # ⚠️ Ignora SSL SOMENTE na SEFAZ (resolve o problema de certificado)
        resp = session.get(qr_url, timeout=(15, 30), verify=False)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        viewstate = soup.find("input", {"name": "__VIEWSTATE"})
        eventvalidation = soup.find("input", {"name": "__EVENTVALIDATION"})
        if not viewstate or not eventvalidation:
            return []

        post_url = "https://nfe.sefaz.ba.gov.br/servicos/nfce/Modulos/Geral/NFCEC_consulta_danfe.aspx"
        data = {
            "__VIEWSTATE": viewstate.get("value", ""),
            "__EVENTVALIDATION": eventvalidation.get("value", ""),
            "btn_visualizar_abas": "Visualizar em Abas",
        }
        resp2 = session.post(post_url, data=data, timeout=(15, 40), verify=False)
        resp2.raise_for_status()

        soup2 = BeautifulSoup(resp2.text, "html.parser")
        viewstate2 = soup2.find("input", {"name": "__VIEWSTATE"})
        eventvalidation2 = soup2.find("input", {"name": "__EVENTVALIDATION"})
        if not viewstate2 or not eventvalidation2:
            return []

        post_url2 = "https://nfe.sefaz.ba.gov.br/servicos/nfce/Modulos/Geral/NFCEC_consulta_abas.aspx"
        data2 = {
            "__VIEWSTATE": viewstate2.get("value", ""),
            "__EVENTVALIDATION": eventvalidation2.get("value", ""),
            "btn_aba_produtos.x": "10",
            "btn_aba_produtos.y": "10",
        }
        resp3 = session.post(post_url2, data=data2, timeout=(15, 40), verify=False)
        resp3.raise_for_status()

        soup3 = BeautifulSoup(resp3.text, "html.parser")

        for prod_table in soup3.select("table.toggle"):
            nome = None
            ean = None

            nome_span = prod_table.select_one("td.fixo-prod-serv-descricao span.multiline")
            if nome_span:
                nome = nome_span.get_text(strip=True)

            toggable = prod_table.find_next_sibling("table", class_="toggable")
            if toggable:
                for tr in toggable.find_all("tr"):
                    labels = tr.find_all("label")
                    spans = tr.find_all("span", class_="linha")
                    for label, span in zip(labels, spans):
                        if "código ean comercial" in (label.get_text(strip=True) or "").lower():
                            ean = (span.get_text(strip=True) or "").strip()

            if nome and ean:
                produtos.append({"nome": nome, "ean": ean})

    except requests.exceptions.RequestException as e:
        print("Erro HTTP:", e)
    except Exception as e:
        print("Erro genérico:", e)

    return produtos

# -------- Rotas ----------
@app.route("/produtos", methods=["POST"])
def produtos_route():
    data = request.get_json(silent=True) or {}
    qr_url = data.get("qr_url", "")
    if not qr_url:
        return jsonify({"erro": "qr_url é obrigatório"}), 400

    itens = extrair_produtos(qr_url)
    return jsonify(itens), 200

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
