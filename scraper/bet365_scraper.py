import asyncio
from playwright.async_api import async_playwright
from thefuzz import fuzz
import re
from datetime import datetime
from typing import List, Dict, Optional
import json


async def scrape_bet365_games(team_filter: Optional[str] = None) -> List[Dict]:
    """
    Scraper para jogos da Bet365 com opção de filtrar por time específico
    
    Args:
        team_filter: Nome do time para filtrar (opcional)
    
    Returns:
        List[Dict]: Lista de jogos com informações extraídas
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        try:
            print("Navegando para Bet365...")
            # Usar a URL funcional descoberta na investigação
            await page.goto('https://www.bet365.bet.br/#/HO/1/', wait_until='networkidle')
            
            # Aguardar carregamento dinâmico
            await asyncio.sleep(5)
            
            # Se um time específico foi solicitado, tentar encontrá-lo
            if team_filter:
                print(f"Procurando jogos do time: {team_filter}")
                team_games = await find_team_games(page, team_filter)
                if team_games:
                    return team_games
                print(f"Time {team_filter} não encontrado, buscando todos os jogos...")
            
            print("Aguardando carregamento completo...")
            await asyncio.sleep(3)
            
            games = []
            
            # Usar múltiplos seletores descobertos na investigação
            game_selectors = [
                '.cpm-MarketFixture',
                '[class*="Fixture"]',
                '.gl-MarketGroup'
            ]
            
            games_found = False
            selector_used = None
            
            for selector in game_selectors:
                try:
                    print(f"Testando seletor: {selector}")
                    game_elements = await page.query_selector_all(selector)
                    
                    if game_elements:
                        print(f"Encontrados {len(game_elements)} elementos com {selector}")
                        games_found = True
                        selector_used = selector
                        
                        for i, element in enumerate(game_elements[:20]):  # Limitar a 20 jogos
                            try:
                                game_text = await element.text_content()
                                if game_text and len(game_text.strip()) > 10:
                                    
                                    # Se há filtro de time, verificar se o jogo contém o time
                                    if team_filter and team_filter.lower() not in game_text.lower():
                                        continue
                                    
                                    # Extrair informações do jogo
                                    game_info = extract_game_info(game_text)
                                    
                                    # Tentar extrair odds usando múltiplos seletores
                                    odds_selectors = [
                                        '.gl-ParticipantOddsOnly_Odds',
                                        '[class*="Odds"]',
                                        '.odds',
                                        '[class*="Price"]'
                                    ]
                                    
                                    odds = []
                                    for odds_selector in odds_selectors:
                                        try:
                                            odds_elements = await element.query_selector_all(odds_selector)
                                            for odds_element in odds_elements:
                                                odds_text = await odds_element.text_content()
                                                if odds_text and re.match(r'^\d+\.\d+$', odds_text.strip()):
                                                    odds.append(float(odds_text.strip()))
                                        except:
                                            continue
                                    
                                    game_data = {
                                        'teams': game_info.get('teams', []),
                                        'date': game_info.get('date'),
                                        'time': game_info.get('time'),
                                        'odds': odds if odds else None,
                                        'raw_text': game_text.strip(),
                                        'source': 'bet365',
                                        'selector_used': selector_used,
                                        'element_index': i,
                                        'team_filter': team_filter
                                    }
                                    
                                    games.append(game_data)
                                    
                            except Exception as e:
                                print(f"Erro ao processar elemento {i}: {e}")
                                continue
                        
                        break  # Sair do loop se encontrou jogos
                        
                except Exception as e:
                    print(f"Erro com seletor {selector}: {e}")
                    continue
            
            if not games_found:
                print("Nenhum jogo encontrado com os seletores disponíveis")
                return [{
                    'teams': [],
                    'date': None,
                    'time': None,
                    'odds': None,
                    'raw_text': 'Nenhum jogo encontrado',
                    'source': 'bet365',
                    'selector_used': None,
                    'note': 'Nenhum seletor funcionou',
                    'team_filter': team_filter
                }]
            
            print(f"Total de jogos extraídos: {len(games)}")
            return games
            
        except Exception as e:
            print(f"Erro no scraping da Bet365: {e}")
            return []
        finally:
            await browser.close()


async def get_bet365_stats(team1: str, team2: str) -> dict:
    """
    Extrai estatísticas ao vivo de uma partida específica no Bet365.
    
    Args:
        team1: Nome do primeiro time
        team2: Nome do segundo time
    
    Returns:
        dict: Estatísticas da partida (escanteios, cartões, etc.)
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        try:
            # Navegar diretamente para a URL que funciona
            await page.goto('https://www.bet365.bet.br/#/HO/1/', wait_until='networkidle')
            await asyncio.sleep(5)
            
            # Aguardar carregamento dinâmico
            await asyncio.sleep(10)
            
            # Procurar por jogos usando os seletores que funcionam
            game_selectors = ['.cpm-MarketFixture', '[class*="Fixture"]', '.gl-MarketGroup']
            
            for selector in game_selectors:
                try:
                    games = await page.query_selector_all(selector)
                    print(f"Encontrados {len(games)} elementos com seletor {selector}")
                    
                    for game in games:
                        game_text = await game.text_content()
                        if game_text and _match_teams(game_text, team1, team2):
                            print(f"Jogo encontrado: {game_text.strip()[:100]}")
                            
                            # Procurar por odds dentro do elemento do jogo
                            odds_selectors = [
                                'span[class*="gl-"]',
                                'span[class*="cpm-"]', 
                                '.gl-Participant_General',
                                '[class*="Odds"]',
                                '[class*="Price"]'
                            ]
                            
                            odds = []
                            for odds_selector in odds_selectors:
                                try:
                                    odds_elements = await game.query_selector_all(odds_selector)
                                    for odd_element in odds_elements:
                                        odd_text = await odd_element.text_content()
                                        if odd_text and odd_text.strip():
                                            # Verificar se parece com uma odd (número decimal)
                                            if '.' in odd_text and odd_text.replace('.', '').isdigit():
                                                odds.append(odd_text.strip())
                                except Exception:
                                    continue
                            
                            if odds:
                                return {
                                    'game': game_text.strip(),
                                    'odds': odds[:6],  # Limitar a 6 odds principais
                                    'source': 'bet365',
                                    'selector_used': selector
                                }
                            else:
                                return {
                                    'game': game_text.strip(),
                                    'odds': [],
                                    'source': 'bet365',
                                    'selector_used': selector,
                                    'note': 'Jogo encontrado mas sem odds'
                                }
                    
                except Exception as e:
                    print(f"Erro com seletor {selector}: {e}")
                    continue
            
            return {'error': f'Jogo {team1} vs {team2} não encontrado'}
            
        except Exception as e:
            return {'error': f'Erro ao acessar Bet365: {str(e)}'}
        finally:
            await browser.close()


def extract_game_info(game_text: str) -> Dict:
    """
    Extrai informações estruturadas do texto do jogo
    
    Args:
        game_text: Texto bruto do jogo
        
    Returns:
        Dict: Informações extraídas (times, data, horário)
    """
    lines = [line.strip() for line in game_text.split('\n') if line.strip()]
    
    teams = []
    date = None
    time = None
    
    for line in lines:
        # Tentar extrair horário (formato HH:MM)
        time_match = re.search(r'\b(\d{1,2}:\d{2})\b', line)
        if time_match and not time:
            time = time_match.group(1)
        
        # Tentar extrair data (vários formatos)
        date_patterns = [
            r'\b(\d{1,2}/\d{1,2}/\d{4})\b',
            r'\b(\d{1,2}-\d{1,2}-\d{4})\b',
            r'\b(\d{4}-\d{1,2}-\d{1,2})\b'
        ]
        
        for pattern in date_patterns:
            date_match = re.search(pattern, line)
            if date_match and not date:
                date = date_match.group(1)
                break
        
        # Tentar extrair nomes de times (linhas que não são números ou datas)
        if (not re.match(r'^[\d\s:/-]+$', line) and 
            len(line) > 3 and 
            not any(keyword in line.lower() for keyword in ['odds', 'bet', 'live', 'ao vivo'])):
            teams.append(line)
    
    return {
        'teams': teams[:2],  # Limitar a 2 times
        'date': date,
        'time': time
    }


def _match_teams(game_text: str, team1: str, team2: str) -> bool:
    """
    Usa fuzzy matching para verificar se o texto do jogo corresponde aos times procurados.
    
    Args:
        game_text: Texto extraído do jogo na página
        team1: Nome do primeiro time
        team2: Nome do segundo time
    
    Returns:
        bool: True se os times correspondem ao jogo
    """
    from thefuzz import fuzz
    
    # Normalizar texto
    game_text = game_text.lower().strip()
    team1_lower = team1.lower().strip()
    team2_lower = team2.lower().strip()
    
    # Verificar se ambos os times estão presentes com similaridade >= 80%
    team1_match = any(fuzz.partial_ratio(team1_lower, line) >= 80 for line in game_text.split('\n'))
    team2_match = any(fuzz.partial_ratio(team2_lower, line) >= 80 for line in game_text.split('\n'))
    
    return team1_match and team2_match


async def find_team_games(page, team_name: str) -> List[Dict]:
    """
    Encontra jogos de um time específico usando múltiplas estratégias
    
    Args:
        page: Página do Playwright
        team_name: Nome do time para buscar
        
    Returns:
        List[Dict]: Lista de jogos do time encontrados
    """
    try:
        print(f"   Procurando {team_name} na página atual...")
        
        # Estratégia 1: Busca direta por texto do time
        team_elements = await page.query_selector_all(f'text=/{team_name}/i')
        
        if team_elements:
            print(f"   ✓ Encontrados {len(team_elements)} elementos com '{team_name}' via busca direta")
        else:
            # Estratégia 2: Navegar para seção de futebol brasileiro
            print(f"   Tentando navegar para futebol brasileiro...")
            
            # Procurar por links de futebol
            football_links = await page.query_selector_all('text=/futebol/i')
            
            for link in football_links:
                try:
                    is_visible = await link.is_visible()
                    if is_visible:
                        text_content = await link.text_content()
                        if text_content and 'futebol' in text_content.lower():
                            print(f"   Clicando em: {text_content.strip()}")
                            await link.click()
                            await asyncio.sleep(3)
                            break
                except Exception as e:
                    print(f"   Erro ao clicar no link de futebol: {e}")
            
            # Procurar por Brasil/Brasileiro
            brasil_links = await page.query_selector_all('text=/brasil/i')
            
            for link in brasil_links:
                try:
                    is_visible = await link.is_visible()
                    if is_visible:
                        text_content = await link.text_content()
                        if text_content and 'brasil' in text_content.lower():
                            print(f"   Clicando em: {text_content.strip()}")
                            await link.click()
                            await asyncio.sleep(3)
                            break
                except Exception as e:
                    print(f"   Erro ao clicar no link do Brasil: {e}")
            
            # Buscar novamente após navegação
            team_elements = await page.query_selector_all(f'text=/{team_name}/i')
            
            if team_elements:
                print(f"   ✓ Encontrados {len(team_elements)} elementos com '{team_name}' após navegação")
        
        # Estratégia 3: Buscar em elementos específicos de jogos se não encontrou ainda
        if not team_elements:
            game_selectors = [
                '.cpm-MarketFixture',
                '[class*="fixture"]',
                '[class*="match"]',
                '[class*="game"]',
                '[class*="event"]'
            ]
            
            for selector in game_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    
                    for element in elements:
                        try:
                            text_content = await element.text_content()
                            if text_content and team_name.lower() in text_content.lower():
                                print(f"   ✓ Time encontrado em elemento {selector}: {text_content.strip()[:100]}...")
                                team_elements.append(element)
                        except Exception:
                            continue
                            
                except Exception as e:
                    print(f"   Erro ao buscar em {selector}: {e}")
        
        if not team_elements:
            print(f"   ✗ Nenhum jogo encontrado para '{team_name}'")
            return []
        
        games = []
        for i, element in enumerate(team_elements):
            try:
                # Tentar encontrar o container do jogo usando XPath
                parent_element = element
                
                # Subir na hierarquia para encontrar o container do jogo
                for _ in range(5):  # Tentar até 5 níveis acima
                    try:
                        parent_element = await parent_element.evaluate('el => el.parentElement')
                        if parent_element:
                            parent_class = await page.evaluate('el => el.className', parent_element)
                            if parent_class and any(keyword in parent_class.lower() for keyword in ['fixture', 'market', 'event', 'game']):
                                game_text = await page.evaluate('el => el.textContent', parent_element)
                                if game_text and len(game_text.strip()) > 10:
                                    game_info = extract_game_info(game_text)
                                    games.append({
                                        'teams': game_info.get('teams', []),
                                        'date': game_info.get('date'),
                                        'time': game_info.get('time'),
                                        'odds': None,  # Será extraído depois se necessário
                                        'raw_text': game_text.strip(),
                                        'source': 'bet365',
                                        'method': 'team_search',
                                        'team_searched': team_name,
                                        'element_index': i
                                    })
                                    break
                    except:
                        break
                
                # Se não encontrou container, usar o próprio elemento
                if not games or len(games) <= i:
                    element_text = await element.text_content()
                    if element_text and len(element_text.strip()) > 5:
                        game_info = extract_game_info(element_text)
                        games.append({
                            'teams': game_info.get('teams', []),
                            'date': game_info.get('date'),
                            'time': game_info.get('time'),
                            'odds': None,
                            'raw_text': element_text.strip(),
                            'source': 'bet365',
                            'method': 'team_search_direct',
                            'team_searched': team_name,
                            'element_index': i
                        })
                        
            except Exception as e:
                print(f"   Erro no elemento {i}: {e}")
        
        return games
        
    except Exception as e:
        print(f"   Erro na busca por time: {e}")
        return []

if __name__ == "__main__":
    import sys
    
    # Verificar se foi passado um time como argumento
    team_filter = None
    if len(sys.argv) > 1:
        team_filter = sys.argv[1]
        print(f"Buscando jogos do time: {team_filter}")
    
    games = asyncio.run(scrape_bet365_games(team_filter))
    
    print(f"\nTotal de jogos encontrados: {len(games)}")
    
    for i, game in enumerate(games, 1):
        print(f"\nJogo {i}:")
        print(f"  Times: {game['teams']}")
        print(f"  Data: {game['date']}")
        print(f"  Horário: {game['time']}")
        print(f"  Odds: {game['odds']}")
        print(f"  Método: {game.get('method', 'N/A')}")
        if team_filter:
            print(f"  Time buscado: {game.get('team_searched', 'N/A')}")
        print(f"  Texto: {game['raw_text'][:100]}...")
    
    # Salvar resultados em JSON
    output_file = f"bet365_games_{team_filter or 'all'}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(games, f, indent=2, ensure_ascii=False)
    print(f"\nResultados salvos em: {output_file}")
    
    # Exemplo de uso da função original
    # result = asyncio.run(get_bet365_stats("Israel", "Itália"))
    # print(f"Estatísticas: {result}")