# Módulo para extrair informações detalhadas dos jogos (ligas, times, etc.)
# Autor: Desenvolvido para enriquecer dados do Kairos Project

import requests
from bs4 import BeautifulSoup
import re
from typing import Dict, List, Optional

# Headers para simular um navegador real
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def get_live_matches_with_details() -> List[Dict]:
    """
    Extrai informações detalhadas dos jogos ao vivo incluindo:
    - ID do jogo
    - Nome da liga/campeonato
    - Times (casa e visitante)
    - Horário do jogo
    - Status (ao vivo, pré-jogo, etc.)
    - País (através da bandeira)
    
    Baseado na estrutura HTML real:
    Célula 1: Bandeira do país (img)
    Célula 2: Nome da liga (class="hide")
    Célula 3: Time da casa
    Célula 4: Placar
    Célula 5: Time visitante
    Célula 6: Tempo do jogo (class="hide")
    
    Returns:
        List[Dict]: Lista com informações detalhadas de cada jogo
    """
    try:
        url = 'https://dropping-odds.com/index.php?view=live'
        response = requests.get(url, headers=HEADERS)
        
        if response.status_code != 200:
            print(f"Erro na requisição: Status code {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        matches = []
        
        # Encontrar todas as linhas da tabela de jogos
        match_rows = soup.find_all('tr', attrs={'game_id': True})
        
        print(f"\n🔍 Analisando {len(match_rows)} jogos na página principal...")
        
        for row in match_rows:
            try:
                game_id = row.get('game_id')
                if not game_id or not game_id.isdigit():
                    continue
                
                match_info = {
                    'game_id': game_id,
                    'league': None,
                    'home_team': None,
                    'away_team': None,
                    'match_time': None,
                    'score': None,
                    'status': 'AO VIVO',
                    'country': None,
                    'country_flag': None
                }
                
                # Extrair informações das células da linha (baseado na estrutura real)
                cells = row.find_all(['td', 'th'])
                
                if len(cells) >= 6:
                    # Célula 1: Bandeira do país
                    country_cell = cells[0]
                    flag_img = country_cell.find('img')
                    if flag_img and flag_img.get('src'):
                        flag_src = flag_img.get('src')
                        match_info['country_flag'] = flag_src
                        # Extrair código do país do nome do arquivo (ex: "cc/br.svg" -> "BR")
                        country_match = re.search(r'/([a-z]{2})\.svg', flag_src)
                        if country_match:
                            match_info['country'] = country_match.group(1).upper()
                    
                    # Célula 2: Liga/Campeonato (class="hide")
                    league_cell = cells[1]
                    league_text = league_cell.get_text(strip=True)
                    if league_text:
                        match_info['league'] = league_text
                    
                    # Célula 3: Time da casa
                    home_cell = cells[2]
                    home_text = home_cell.get_text(strip=True)
                    if home_text:
                        match_info['home_team'] = home_text
                    
                    # Célula 4: Placar
                    score_cell = cells[3]
                    score_text = score_cell.get_text(strip=True)
                    if score_text:
                        match_info['score'] = score_text
                    
                    # Célula 5: Time visitante
                    away_cell = cells[4]
                    away_text = away_cell.get_text(strip=True)
                    if away_text:
                        match_info['away_team'] = away_text
                    
                    # Célula 6: Tempo do jogo (class="hide")
                    if len(cells) > 5:
                        time_cell = cells[5]
                        time_text = time_cell.get_text(strip=True)
                        if time_text:
                            match_info['match_time'] = time_text
                
                matches.append(match_info)
                
                # Debug: mostrar informações extraídas
                print(f"  📋 Jogo {game_id}:")
                print(f"     País: {match_info['country'] or 'N/A'} ({match_info['country_flag'] or 'N/A'})")
                print(f"     Liga: {match_info['league'] or 'N/A'}")
                print(f"     Partida: {match_info['home_team'] or 'N/A'} vs {match_info['away_team'] or 'N/A'}")
                print(f"     Placar: {match_info['score'] or 'N/A'}")
                print(f"     Tempo: {match_info['match_time'] or 'N/A'}")
                print()
                
            except Exception as e:
                print(f"  ⚠️ Erro ao processar jogo {game_id}: {e}")
                continue
        
        print(f"✅ Extraídas informações de {len(matches)} jogos")
        return matches
        
    except Exception as e:
        print(f"Erro durante extração de informações: {e}")
        return []

def get_match_details(game_id: str) -> Optional[Dict]:
    """
    Extrai informações detalhadas de um jogo específico da sua página individual.
    
    Args:
        game_id (str): ID do jogo
        
    Returns:
        Optional[Dict]: Informações detalhadas do jogo ou None se não encontrado
    """
    try:
        url = f'https://dropping-odds.com/event.php?id={game_id}'
        response = requests.get(url, headers=HEADERS)
        
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        match_info = {
            'game_id': game_id,
            'league': None,
            'home_team': None,
            'away_team': None,
            'match_time': None,
            'match_date': None,
            'status': None,
            'country': None
        }
        
        # Procurar pelo título da página ou cabeçalho principal
        title_elements = soup.find_all(['h1', 'h2', 'title', '.match-title', '.event-title'])
        for element in title_elements:
            text = element.get_text(strip=True)
            if text and (' vs ' in text or ' - ' in text):
                if ' vs ' in text:
                    teams = text.split(' vs ')
                elif ' - ' in text:
                    teams = text.split(' - ')
                
                if len(teams) == 2:
                    match_info['home_team'] = teams[0].strip()
                    match_info['away_team'] = teams[1].strip()
                    break
        
        # Procurar informações de liga/campeonato
        league_selectors = [
            '.league', '.competition', '.tournament',
            '[class*="league"]', '[class*="competition"]'
        ]
        
        for selector in league_selectors:
            league_element = soup.select_one(selector)
            if league_element:
                league_text = league_element.get_text(strip=True)
                if league_text:
                    match_info['league'] = league_text
                    break
        
        return match_info
        
    except Exception as e:
        print(f"Erro ao extrair detalhes do jogo {game_id}: {e}")
        return None

def find_team_in_matches(team_name: str, matches: List[Dict]) -> List[Dict]:
    """
    Encontra jogos que contêm um time específico.
    
    Args:
        team_name (str): Nome do time para buscar
        matches (List[Dict]): Lista de jogos para pesquisar
        
    Returns:
        List[Dict]: Lista de jogos que contêm o time
    """
    found_matches = []
    team_lower = team_name.lower().strip()
    
    for match in matches:
        home_team = (match.get('home_team') or '').lower().strip()
        away_team = (match.get('away_team') or '').lower().strip()
        
        # Verificar correspondência exata ou parcial
        if (team_lower in home_team or home_team in team_lower or
            team_lower in away_team or away_team in team_lower):
            found_matches.append(match)
    
    return found_matches

if __name__ == "__main__":
    # Teste da funcionalidade
    print("🔍 Testando extração de informações dos jogos...")
    matches = get_live_matches_with_details()
    
    if matches:
        print(f"\n📊 RESUMO: {len(matches)} jogos encontrados")
        print("\n" + "="*60)
        
        for match in matches[:5]:  # Mostrar apenas os primeiros 5
            print(f"🎯 Jogo ID: {match['game_id']}")
            print(f"   Liga: {match['league'] or 'N/A'}")
            print(f"   Partida: {match['home_team'] or 'N/A'} vs {match['away_team'] or 'N/A'}")
            print(f"   Horário: {match['match_time'] or 'N/A'}")
            print(f"   Status: {match['status'] or 'N/A'}")
            print()
    else:
        print("❌ Nenhum jogo encontrado")