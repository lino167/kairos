# Script para web scraping do site Dropping-Odds
# Autor: Desenvolvido para coleta de dados de odds em tempo real

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import re

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

def get_available_table_types(match_id):
    """
    Detecta automaticamente os tipos de tabela disponíveis para um evento específico.
    
    Args:
        match_id (str): ID do jogo para verificar
        
    Returns:
        list: Lista de tipos de tabela disponíveis (ex: ['1x2', 'total', 'handicap'])
    """
    try:
        # URL padrão do evento
        event_url = f'https://dropping-odds.com/event.php?id={match_id}'
        
        # Headers para simular navegador
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        print(f"Verificando tipos de tabela disponíveis para evento {match_id}...")
        
        # Fazer requisição
        response = requests.get(event_url, headers=headers)
        response.raise_for_status()
        
        # Analisar HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Procurar pelo menu de tipos de tabela
        menu_div = soup.find('div', class_='smenu')
        if not menu_div:
            print("Menu de tipos não encontrado, usando tipos padrão")
            return ['1x2', 'total', 'handicap', 'total_ht', '1x2_ht']
        
        # Extrair tipos de tabela dos links
        table_types = []
        links = menu_div.find_all('a', href=True)
        
        for link in links:
            href = link.get('href', '')
            # Procurar por parâmetro t= na URL
            match = re.search(r't=([^&]+)', href)
            if match:
                table_type = match.group(1)
                table_types.append(table_type)
                print(f"  Encontrado tipo: {table_type}")
        
        if not table_types:
            print("Nenhum tipo específico encontrado, usando padrão")
            return ['1x2', 'total', 'handicap', 'total_ht', '1x2_ht']
        
        print(f"Tipos disponíveis: {table_types}")
        return table_types
        
    except Exception as e:
        print(f"Erro ao detectar tipos de tabela: {e}")
        return ['1x2', 'total', 'handicap', 'total_ht', '1x2_ht']


def scrape_event_page(match_id, table_type=None):
    """
    Faz scraping de uma página específica de evento e retorna as tabelas como DataFrames.
    
    Args:
        match_id (str): ID do jogo para fazer scraping
        table_type (str, opcional): Tipo de tabela para extrair. Opções:
            - None: Página padrão do evento (dados de total/over-under)
            - 'total': Odds de total de gols (Over/Under)
            - 'handicap': Odds de handicap asiático
            - 'total_ht': Odds de total de gols no primeiro tempo
            - '1x2_ht': Odds 1x2 do primeiro tempo
            - '1x2': Odds 1x2 (Casa/Empate/Fora) - pode não funcionar
    
    Returns:
        list: Lista de DataFrames do pandas contendo as tabelas da página
    """
    try:
        # Construir a URL do evento baseada no tipo de tabela
        event_url = f'https://dropping-odds.com/event.php?id={match_id}'
        if table_type:
            event_url += f'&t={table_type}'
        
        table_desc = f" ({table_type})" if table_type else ""
        print(f"Fazendo scraping da página do evento: {event_url}")
        
        # Usar pandas para extrair tabelas diretamente da URL
        tables = pd.read_html(event_url, header=0)
        
        print(f"Encontradas {len(tables)} tabelas na página do evento{table_desc}")
        return tables
        
    except Exception as e:
        table_desc = f" ({table_type})" if table_type else ""
        print(f"Erro ao fazer scraping da página do evento {match_id}{table_desc}: {e}")
        return []

# Função principal (a ser implementada)
def main():
    """
    Função principal para executar o web scraping
    """
    pass

def find_significant_drop(tables, threshold=10.0):
    """
    Procura por drops significativos nas tabelas extraídas.
    
    Args:
        tables (list): Lista de DataFrames
        threshold (float): Limiar mínimo para considerar um drop significativo
                          Para colunas Drop: valores absolutos (ex: 0.5 para 50%)
                          Para colunas %: valores em percentual (ex: 10.0 para 10%)
        
    Returns:
        tuple: (bool, DataFrame ou None) - True se encontrou oportunidade, False caso contrário
    """
    target_columns = ['drop', 'sharp', 'home%', 'away%', 'sharpness']
    
    for table in tables:
        if table is None or table.empty:
            continue
            
        # Procurar colunas que contenham as palavras-chave (case insensitive)
        for col_name in table.columns:
            col_lower = col_name.lower()
            
            # Verificar se a coluna contém alguma das palavras-chave
            if any(keyword in col_lower for keyword in target_columns):
                print(f"Analisando coluna: {col_name}")
                
                # Iterar sobre os valores da coluna
                for value in table[col_name]:
                    if pd.isna(value) or value == '' or value == '-':
                        continue
                        
                    try:
                        # Limpar o valor: remover % e converter para float
                        clean_value = str(value).replace('%', '').replace(',', '.').strip()
                        numeric_value = float(clean_value)
                        
                        # Ajustar threshold baseado no tipo de coluna
                        if '%' in col_lower:
                            # Para colunas de percentual, usar threshold direto
                            effective_threshold = threshold
                        else:
                            # Para colunas Drop/Sharp, converter threshold para decimal
                            # Ex: threshold 10.0 vira 0.10 (10%)
                            effective_threshold = threshold / 100.0
                        
                        # Verificar se atende ao threshold (valor absoluto para drops negativos)
                        if abs(numeric_value) >= effective_threshold:
                            print(f"OPORTUNIDADE DETECTADA: {col_name} = {value} (|{numeric_value}| >= {effective_threshold})")
                            return True, table
                            
                    except (ValueError, TypeError):
                        # Ignorar valores que não podem ser convertidos
                        continue
    
    return False, None


def scrape_all_available_tables(match_id):
    """
    Faz scraping de todos os tipos de tabela disponíveis para um evento.
    
    Args:
        match_id (str): ID do jogo para fazer scraping
        
    Returns:
        dict: Dicionário com tipos de tabela como chaves e DataFrames como valores
    """
    print(f"\n{'='*60}")
    print(f"Fazendo scraping completo do evento: {match_id}")
    print(f"{'='*60}")
    
    # Detectar tipos disponíveis
    available_types = get_available_table_types(match_id)
    
    results = {}
    all_tables = []  # Lista para armazenar todas as tabelas
    
    for table_type in available_types:
        print(f"\n{'='*40}")
        print(f"Extraindo tabela: {table_type}")
        print(f"{'='*40}")
        
        tables = scrape_event_page(match_id, table_type)
        
        if tables:
            # Assumir que há apenas uma tabela principal por tipo
            main_table = tables[0] if tables else None
            if main_table is not None and not main_table.empty:
                results[table_type] = main_table
                all_tables.extend(tables)  # Adiciona todas as tabelas à lista
                print(f"✓ Tabela {table_type}: {main_table.shape[0]} linhas x {main_table.shape[1]} colunas")
                print(f"  Colunas: {list(main_table.columns)}")
                print(f"  Amostra:")
                print(main_table.head(2).to_string(index=False))
            else:
                print(f"✗ Tabela {table_type}: vazia")
        else:
            print(f"✗ Tabela {table_type}: não encontrada")
    
    print(f"\n{'='*60}")
    print(f"Scraping concluído! Extraídas {len(results)} tabelas")
    print(f"Tipos extraídos: {list(results.keys())}")
    print(f"{'='*60}")
    
    return results, all_tables


if __name__ == "__main__":
    # Testar o scraper
    live_matches = get_live_match_ids()
    
    if live_matches:
        print(f"Encontradas {len(live_matches)} partidas ao vivo")
        
        # Testar com a primeira partida
        first_match = live_matches[0]
        print(f"\nTestando com a partida: {first_match}")
        
        # Extrair todas as tabelas disponíveis
        all_tables_dict, all_tables_list = scrape_all_available_tables(first_match)
        
        print(f"\n{'='*60}")
        print("RESUMO FINAL")
        print(f"{'='*60}")
        for table_type, table in all_tables_dict.items():
            if table is not None:
                print(f"{table_type}: {table.shape[0]} linhas x {table.shape[1]} colunas")
        
        # Procurar por oportunidades significativas
        print(f"\n{'='*60}")
        print("ANÁLISE DE OPORTUNIDADES")
        print(f"{'='*60}")
        
        found_opportunity, opportunity_table = find_significant_drop(all_tables_list, threshold=10.0)
        
        if found_opportunity:
            print("\n🚨 OPORTUNIDADE ENCONTRADA! 🚨")
            print("Tabela com drop significativo:")
            print(f"Colunas: {list(opportunity_table.columns)}")
            print(f"Dimensões: {opportunity_table.shape[0]} linhas x {opportunity_table.shape[1]} colunas")
            print("\nPrimeiras linhas da tabela:")
            print(opportunity_table.head())
        else:
            print("Nenhuma oportunidade significativa encontrada com o threshold atual.")
            
    else:
        print("Nenhuma partida ao vivo encontrada")