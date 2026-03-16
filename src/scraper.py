import asyncio
import hashlib
import time
from playwright.async_api import async_playwright

class KairosScraper:
    MARKETS = [
        {"name": "1X2", "id": "1x2", "cols": {"time": 1, "score": 2, "1": 3, "X": 4, "2": 5, "penalty": 8, "red": 9}},
        {"name": "TOTAL", "id": "total", "cols": {"time": 1, "score": 2, "over": 3, "line": 4, "under": 5, "penalty": 8, "red": 9}},
        {"name": "HANDICAP", "id": "handicap", "cols": {"time": 1, "score": 2, "1": 3, "line": 4, "2": 5, "penalty": 7, "red": 8}},
        {"name": "HT TOTAL", "id": "total_ht", "cols": {"time": 1, "score": 2, "over": 3, "line": 4, "under": 5, "penalty": 7, "red": 8}},
        {"name": "HT 1X2", "id": "1x2_ht", "cols": {"time": 1, "score": 2, "1": 3, "X": 4, "2": 5, "penalty": 8, "red": 9}}
    ]

    def __init__(self, headless=False):
        self.headless = headless

    async def get_live_game_ids(self, page):
        """Captura os IDs das partidas. v2.9: Remove filtro de Home pois as colunas estao ocultas."""
        try:
            await page.goto("https://dropping-odds.com/index.php?view=live", wait_until="networkidle", timeout=60000)
            await page.wait_for_selector("tr.a_link", timeout=15000)
            
            game_rows = await page.query_selector_all("tr.a_link")
            ids = []
            # v2.9: Coletar todos (limitado a 40 para performance e restaurar navegacao)
            for row in game_rows[:40]:
                gid = await row.get_attribute("game_id")
                if gid: ids.append(gid)
            
            print(f"    [*] Home scan: {len(game_rows)} encontrados. Processando Top {len(ids)}.")
            return ids
        except Exception as e:
            print(f"    [!] Erro ao capturar IDs de jogos: {e}")
            return []

    async def scan_game_details(self, page, gid):
        """Nova lógica: Escaneia TODOS os mercados e retorna um snapshot completo com todo o histórico da tabela."""
        base_url = f"https://dropping-odds.com/event.php?id={gid}"
        match_snapshot = {
            "gid": gid,
            "match_name": "Unknown",
            "live_score": "0-0",
            "markets": {},
            "has_anomalies": False,
            "is_red3": False
        }
        
        for m_info in self.MARKETS:
            url = f"{base_url}&t={m_info['id']}"
            try:
                print(f"    -> Coletando histórico de: {m_info['name']}...", flush=True)
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(200)
                
                try:
                    # Tentar encontrar a tabela de odds (geralmente a única com dados significativos)
                    await page.wait_for_selector("table tr", timeout=5000)
                except: continue

                # Capturar info básica apenas na primeira vez
                if match_snapshot["match_name"] == "Unknown":
                    header_text = await page.inner_text("div.matchinfo")
                    lines = [l.strip() for l in header_text.split('\n') if l.strip()]
                    match_snapshot["league_name"] = lines[0] if len(lines) > 0 else "Liga Desconhecida"
                    match_snapshot["match_name"] = lines[1] if len(lines) > 1 else lines[0]
                    try:
                        match_snapshot["live_score"] = (await page.inner_text("div.matchinfo font.score")).replace(':', '-')
                    except: pass

                # Extrair dados da tabela completa
                market_data = {"history": [], "opening_odds": None, "current_main_line": None, "is_suspended": False}
                
                # Selecionar a tabela principal (que não seja oculta)
                rows = await page.query_selector_all("table:not(.hide) tr")
                cols = m_info['cols']
                
                for row_idx, row in enumerate(rows):
                    if row_idx == 0: continue # Header
                    
                    all_tds = await row.query_selector_all("td")
                    if len(all_tds) <= max(cols.values()): continue

                    row_time = (await all_tds[cols['time']].inner_text()).strip()
                    row_score = (await all_tds[cols['score']].inner_text()).strip()
                    
                    # Extração de Penalties e Vermelhos
                    has_penalty = True if await all_tds[cols['penalty']].query_selector("img") else False
                    has_red = True if await all_tds[cols['red']].query_selector("img") else False
                    row_line = (await all_tds[cols['line']].inner_text()).strip() if 'line' in cols else "N/A"

                    # Capturar valores reais das Odds
                    selection_values = {}
                    drop_info = None
                    
                    target_cols = ["1", "X", "2", "over", "under"]
                    for tc in target_cols:
                        if tc in cols:
                            idx = cols[tc]
                            val = (await all_tds[idx].inner_text()).strip()
                            selection_values[tc] = val
                            
                            # Se for a célula que dropou
                            cls = await all_tds[idx].get_attribute("class") or ""
                            if "red" in cls:
                                drop_info = {"selection": tc, "value": val}
                                if "red3" in cls or "RED3" in cls:
                                    match_snapshot["is_red3"] = True

                    # Identificar se é Pré-Live ou Live
                    state = "Live"
                    if not row_time and not row_score:
                        state = "Pre-Live"
                    
                    market_data["history"].append({
                        "time": row_time or "N/A",
                        "score": row_score or "0-0",
                        "line": row_line,
                        "selection_values": selection_values,
                        "drop_info": drop_info,
                        "penalty": has_penalty,
                        "red_card": has_red,
                        "state": state
                    })

                    if drop_info:
                        match_snapshot["has_anomalies"] = True

                # Coletar Dados de Abertura e Linha Atual
                if len(rows) > 1:
                    first_data_tds = await rows[1].query_selector_all("td") if len(rows) > 1 else []
                    if len(first_data_tds) > 3:
                        market_data["is_suspended"] = not (await first_data_tds[3].inner_text()).strip()

                match_snapshot["markets"][m_info['name']] = market_data

            except Exception as e:
                print(f"    [!] Erro no mercado {m_info['name']}: {e}")

        # v2.9: Se o usuário quer apenas Red3, filtramos aqui se nada foi detectado
        return match_snapshot if match_snapshot["is_red3"] else None
    async def check_final_score(self, page, gid):
        """Verifica se a partida chegou aos 90' e retorna o placar final se sim."""
        url = f"https://dropping-odds.com/event.php?id={gid}&t=1x2"
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(200)
            
            # Pegar a primeira linha da tabela (mais recente)
            row = await page.query_selector("table:not(.hide) tr:nth-child(2)")
            if not row: return None
            
            all_tds = await row.query_selector_all("td")
            if len(all_tds) < 3: return None
            
            time_text = (await all_tds[1].inner_text()).strip()
            score_text = (await all_tds[2].inner_text()).strip()
            
            # Logica: se o minuto for 90, 90+, ou se estiver vazio (fim de jogo as vezes limpa)
            # Na dropping-odds, 90:00 costuma ser o limite.
            if "90" in time_text or (not time_text and score_text):
                return score_text.replace(':', '-')
            
            return None
        except:
            return None
