# Script para web scraping do site Dropping-Odds
# Autor: Desenvolvido para coleta de dados de odds em tempo real

import requests
from bs4 import BeautifulSoup
import pandas as pd

# URL constante para a página de odds ao vivo
URL_LIVE = 'https://dropping-odds.com/index.php?view=live'

# Headers para simular um navegador real
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def get_live_match_ids():
    """
    Extrai os IDs dos jogos ao vivo do site Dropping-Odds
    
    Returns:
        list: Lista com os IDs dos jogos encontrados
    """
    try:
        # Fazer requisição GET para a URL
        response = requests.get(URL_LIVE, headers=HEADERS)
        
        # Verificar se a resposta foi bem-sucedida
        if response.status_code != 200:
            print(f"Erro na requisição: Status code {response.status_code}")
            return []
        
        # Parsear o conteúdo HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Encontrar todas as linhas da tabela que contêm o atributo 'game_id'
        match_rows = soup.find_all('tr', attrs={'game_id': True})
        
        # Lista para armazenar os IDs dos jogos
        match_ids = []
        
        # Iterar sobre as linhas encontradas
        for row in match_rows:
            game_id = row.get('game_id')
            if game_id and game_id.isdigit():
                match_ids.append(game_id)
        
        return match_ids
        
    except Exception as e:
        print(f"Erro durante o web scraping: {e}")
        return []

def scrape_event_page(match_id):
    """
    Extrai as tabelas de uma página específica de evento
    
    Args:
        match_id (str): ID do jogo para construir a URL do evento
    
    Returns:
        list: Lista de DataFrames com as tabelas da página, ou lista vazia se falhar
    """
    try:
        # Construir a URL do evento
        event_url = f'https://dropping-odds.com/event.php?id={match_id}&t=1x2'
        
        print(f"Fazendo scraping da página do evento: {event_url}")
        
        # Usar pandas para extrair tabelas diretamente da URL
        tables = pd.read_html(event_url, header=0)
        
        print(f"Encontradas {len(tables)} tabelas na página do evento")
        return tables
        
    except Exception as e:
        print(f"Erro ao fazer scraping da página do evento {match_id}: {e}")
        return []

# Função principal (a ser implementada)
def main():
    """
    Função principal para executar o web scraping
    """
    pass

if __name__ == "__main__":
    # Testar a função get_live_match_ids
    match_ids = get_live_match_ids()
    print(f"IDs dos jogos encontrados: {match_ids}")
    print(f"Total de jogos: {len(match_ids)}")
    
    # Testar scraping da página do primeiro evento
    if match_ids:
        first_match_id = match_ids[0]
        print(f"\nFazendo scraping do primeiro jogo (ID: {first_match_id})...")
        
        event_tables = scrape_event_page(first_match_id)
        
        if event_tables:
            print(f"\n=== TABELAS ENCONTRADAS NA PÁGINA DO EVENTO ===")
            for i, table in enumerate(event_tables):
                print(f"\nTabela {i+1}:")
                print(f"Dimensões: {table.shape}")
                print(f"Colunas: {list(table.columns)}")
                print("Primeiras linhas:")
                print(table.head())
                print("-" * 50)
        else:
            print("Nenhuma tabela encontrada na página do evento")
    else:
        print("Nenhum ID de jogo encontrado para testar")