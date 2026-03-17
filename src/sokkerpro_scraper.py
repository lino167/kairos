import asyncio
import re
from typing import Dict, Optional
from playwright.async_api import Page

class SokkerProScraper:
    BASE_URL = "https://sokkerpro.com/"

    async def search_match(self, page: Page, home: str, away: str) -> Dict:
        """Busca uma partida no SokkerPro e abre os detalhes."""
        try:
            print(f"[*] [SOKKERPRO] Buscando: {home} vs {away}...")
            if page.url == "about:blank" or not page.url.startswith(self.BASE_URL):
                await page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=60000)
            
            # Limpar busca
            search_input = await page.wait_for_selector(".desktop-search-input", timeout=10000)
            await search_input.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            
            await search_input.fill(home)
            await page.wait_for_timeout(3000)
            
            # Selecionar a terceira opção conforme solicitado
            results = await page.query_selector_all(".fixture-item, .match-item, .match-card")
            match_item = None
            
            if len(results) >= 3:
                print(f"    [*] Selecionando a terceira opção (de {len(results)} resultados)...")
                match_item = results[2]
            elif len(results) > 0:
                print(f"    [*] Menos de 3 resultados encontrados ({len(results)}). Selecionando o primeiro...")
                match_item = results[0]
            else:
                # Fallback para busca por texto se os seletores de classe falharem
                match_item = await page.query_selector(f"text='{home}'")
                if not match_item:
                    match_item = await page.query_selector(f"text='{away}'")

            if match_item:
                await match_item.click()
                await page.wait_for_timeout(2000)
                print(f"    [+] Partida selecionada.")
                return {"found": True}
            
            print(f"    [-] Partida não encontrada na lista.")
            return {"found": False}
        except Exception as e:
            print(f"[!] [SOKKERPRO] Erro na busca: {e}")
            return {"found": False}

    async def get_live_stats(self, page: Page) -> Optional[Dict]:
        """Extrai as estatísticas live (APPM, Ataques, etc.)."""
        try:
            panel = await page.wait_for_selector(".desktop-details-panel", timeout=8000)
            if not panel: return None

            # Garantir aba correta (pode ser 'AO VIVO' ou 'ESTATÍSTICAS')
            live_tab = await panel.query_selector("button.tab-button:has-text('AO VIVO')")
            if not live_tab:
                live_tab = await panel.query_selector("button.tab-button:has-text('ESTATÍSTICAS')")
            
            if live_tab and "active" not in await live_tab.get_attribute("class"):
                await live_tab.click()
                await page.wait_for_timeout(1500)

            stats = {
                "ataques": {"home": 0, "away": 0},
                "ataques_perigosos": {"home": 0, "away": 0},
                "posse": {"home": 50, "away": 50},
                "appm_5m": {"home": 0.0, "away": 0.0},
                "appm_10m": {"home": 0.0, "away": 0.0},
                "score_raw": "0-0"
            }

            # Extração via busca de label e vizinhos
            async def find_values_by_label(label):
                try:
                    # Encontrar o elemento que contém o label
                    label_el = await panel.query_selector(f"text='{label}'")
                    if label_el:
                        # No SokkerPRO, os valores costumam estar em elementos irmãos ou container pai
                        parent = await label_el.query_selector("xpath=..")
                        if parent:
                            # Tentar pegar todos os números dentro deste container
                            texts = await parent.inner_text()
                            nums = re.findall(r"(\d+\.?\d*)", texts)
                            if len(nums) >= 3: # h_val, label, a_val
                                return nums[0], nums[2]
                            elif len(nums) == 2:
                                return nums[0], nums[1]
                except: pass
                return None, None

            h, a = await find_values_by_label("Ataques Perigosos")
            if h: stats["ataques_perigosos"] = {"home": int(h), "away": int(a)}
            
            h, a = await find_values_by_label("Ataques")
            if h: stats["ataques"] = {"home": int(h), "away": int(a)}
            
            h, a = await find_values_by_label("% de Posse")
            if h: stats["posse"] = {"home": int(h), "away": int(a)}

            # APPM (Ataques Perigosos Por Minuto)
            h, a = await find_values_by_label("APPM 5m")
            if not h: h, a = await find_values_by_label("APPM 5 MIN")
            if h: stats["appm_5m"] = {"home": float(h), "away": float(a)}

            h, a = await find_values_by_label("APPM 10m")
            if not h: h, a = await find_values_by_label("APPM 10 MIN")
            if h: stats["appm_10m"] = {"home": float(h), "away": float(a)}

            return stats
        except Exception as e:
            print(f"[!] [SOKKERPRO] Erro ao extrair stats live: {e}")
            return None

    async def get_prelive_stats(self, page: Page) -> Optional[Dict]:
        """Extrai médias históricas da aba PRÉ JOGO."""
        try:
            panel = await page.wait_for_selector(".desktop-details-panel", timeout=5000)
            pre_tab = await panel.query_selector("button.tab-button:has-text('PRÉ JOGO')")
            if pre_tab:
                await pre_tab.click()
                await page.wait_for_timeout(1500)

            stats = {"avg_goals": 0.0}
            # Buscar média de gols
            res = await panel.query_selector("text='GOLS'")
            if res:
                # Pegar o valor próximo
                parent = await res.query_selector("xpath=..")
                if parent:
                    text = await parent.inner_text()
                    matches = re.findall(r"(\d+\.\d+)", text)
                    if matches: stats["avg_goals"] = float(matches[0])
            
            return stats
        except Exception as e:
            print(f"[!] [SOKKERPRO] Erro ao extrair pre-live: {e}")
            return None
