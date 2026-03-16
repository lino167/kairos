import asyncio
import re
import unicodedata
from typing import List, Dict, Optional
from playwright.async_api import Page

def normalize_name(text: str) -> str:
    """Remove acentos, converte para minúsculas e simplifica nomes de times."""
    if not text: return ""
    text = "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    text = text.lower()
    # Remover sufixos e prefixos comuns
    patterns = [r"\bclube\b", r"\bfutebol\b", r"\bclub\b", r"\bfc\b", r"\bu\d+\b", r"\bsub-\d+\b"]
    for p in patterns:
        text = re.sub(p, "", text)
    return re.sub(r"\s+", " ", text).strip()

class ExcapperScraper:
    BASE_URL = "https://www.excapper.com/"
    LIVE_URL = "https://www.excapper.com/#live"

    async def get_live_matches(self, page: Page) -> List[Dict]:
        """Extrai a lista de partidas ao vivo do Money Way."""
        matches = []
        try:
            print("[*] [EXCAPPER] Acessando lista live...")
            await page.goto(self.LIVE_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)

            # Selecionar a aba Live se não estiver ativa
            rows = await page.query_selector_all("tr.a_link")
            print(f"[*] [EXCAPPER] Encontrados {len(rows)} jogos potenciais.")

            for row in rows:
                cols = await row.query_selector_all("td")
                if len(cols) < 5: continue

                # Identificar game_id nos novos atributos observados
                game_id = await row.get_attribute("game_id")
                
                if not game_id:
                    data_link = await row.get_attribute("data-game-link")
                    if data_link:
                        match = re.search(r"id=(\d+)", data_link)
                        if match: game_id = match.group(1)

                if not game_id: continue

                teams_text = (await cols[3].inner_text()).strip()
                match_data = {
                    "game_id": game_id,
                    "teams": teams_text,
                    "total_money": (await cols[4].inner_text()).strip(),
                    "league": (await cols[2].inner_text()).strip(),
                    "url": f"{self.BASE_URL}?action=game&id={game_id}"
                }
                matches.append(match_data)
                print(f"    [+] Jogo encontrado: {teams_text} (ID: {game_id})")
            
            return matches
        except Exception as e:
            print(f"[!] [EXCAPPER] Erro ao listar jogos: {e}")
            return []

    async def get_match_flow(self, page: Page, game_id: str) -> Dict[str, Dict]:
        """Extrai o histórico de fluxo de dinheiro e odds de TODOS os mercados do jogo."""
        all_markets_data = {}
        url = f"{self.BASE_URL}?action=game&id={game_id}"
        try:
            print(f"[*] [EXCAPPER] Acessando detalhes do jogo {game_id}...")
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(3000)

            # Mapear abas para nomes de mercados e IDs da Betfair
            tabs = await page.query_selector_all("a.tab")
            market_meta = {}
            for tab in tabs:
                href = await tab.get_attribute("href")
                data_tab = await tab.get_attribute("data-tab")
                
                # O ID costuma estar no href ou data-tab como tab_content_XXXXXXXXX
                target_id = data_tab or (href.lstrip("#") if href and href.startswith("#") else None)
                
                if target_id:
                    name = (await tab.inner_text()).strip()
                    bf_id = target_id.replace("tab_content_", "")
                    market_meta[target_id] = {
                        "name": name,
                        "bf_id": bf_id,
                        "bf_url": f"https://www.betfair.com/exchange/plus/football/market/1.{bf_id}"
                    }

            # Iterar por todos os containers de conteúdo de mercado
            containers = await page.query_selector_all("div[id^='tab_content_']")
            print(f"[*] [EXCAPPER] Encontrados {len(containers)} mercados para extração.")

            for container in containers:
                tab_id = await container.get_attribute("id")
                meta = market_meta.get(tab_id)
                if not meta: continue
                
                market_name = meta["name"]
                
                rows = await container.query_selector_all("table tr")
                if not rows: continue

                market_flow = []
                # Ignorar cabeçalho
                for row in rows[1:]:
                    cols = await row.query_selector_all("td")
                    if len(cols) < 9: continue

                    # Extrair Change (EUR)
                    change_raw = (await cols[4].inner_text()).strip()
                    change_val = 0.0
                    match_val = re.search(r"([\d\.,]+)€", change_raw)
                    if match_val:
                        change_val = float(match_val.group(1).replace(",", ""))

                    market_flow.append({
                        "selection": (await cols[2].inner_text()).strip(), # Ex: Over 2.5, Home, Yes
                        "change_eur": change_val,
                        "time": (await cols[5].inner_text()).strip(),
                        "score": (await cols[6].inner_text()).strip(),
                        "odds": (await cols[7].inner_text()).strip(),
                        "change_pct": (await cols[8].inner_text()).strip()
                    })
                
                if market_flow:
                    all_markets_data[market_name] = {
                        "market_id": meta["bf_id"],
                        "betfair_url": meta["bf_url"],
                        "flow": market_flow
                    }
            
            return all_markets_data
        except Exception as e:
            print(f"[!] [EXCAPPER] Erro ao extrair fluxos {game_id}: {e}")
            return {}
