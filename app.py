from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import os

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

def extrair_produtos(qr_url):
    session = requests.Session()
    produtos = []
    try:
        resp = session.get(qr_url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        viewstate = soup.find('input', {'name': '__VIEWSTATE'})
        eventvalidation = soup.find('input', {'name': '__EVENTVALIDATION'})
        if not viewstate or not eventvalidation:
            return []
        post_url = "http://nfe.sefaz.ba.gov.br/servicos/nfce/Modulos/Geral/NFCEC_consulta_danfe.aspx"
        data = {
            '__VIEWSTATE': viewstate['value'],
            '__EVENTVALIDATION': eventvalidation['value'],
            'btn_visualizar_abas': 'Visualizar em Abas'
        }
        resp2 = session.post(post_url, data=data, timeout=10)
        soup2 = BeautifulSoup(resp2.text, 'html.parser')
        viewstate2 = soup2.find('input', {'name': '__VIEWSTATE'})
        eventvalidation2 = soup2.find('input', {'name': '__EVENTVALIDATION'})
        if not viewstate2 or not eventvalidation2:
            return []
        data2 = {
            '__VIEWSTATE': viewstate2['value'],
            '__EVENTVALIDATION': eventvalidation2['value'],
            'btn_aba_produtos.x': '10',
            'btn_aba_produtos.y': '10'
        }
        post_url2 = "http://nfe.sefaz.ba.gov.br/servicos/nfce/Modulos/Geral/NFCEC_consulta_abas.aspx"
        resp3 = session.post(post_url2, data=data2, timeout=10)
        soup3 = BeautifulSoup(resp3.text, 'html.parser')
        for prod_table in soup3.select('table.toggle'):
            nome = None
            ean = None
            nome_span = prod_table.select_one('td.fixo-prod-serv-descricao span.multiline')
            if nome_span:
                nome = nome_span.text.strip()
            toggable = prod_table.find_next_sibling('table', class_='toggable')
            if toggable:
                for td in toggable.find_all('td'):
                    label = td.find('label')
                    valor = td.find('span', class_='linha')
                    if label and valor and 'Código EAN Comercial' in label.text:
                        ean = valor.text.strip()
            if nome and ean:
                produtos.append({'nome': nome, 'ean': ean})
    except Exception as e:
        print("Erro:", e)
    return produtos

@app.route('/produtos', methods=['POST'])
def produtos():
    data = request.get_json()
    qr_url = data.get('qr_url')
    produtos = extrair_produtos(qr_url)
    return jsonify(produtos)

# Servir o index.html e arquivos estáticos
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    app.run(debug=True)