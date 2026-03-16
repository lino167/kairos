import asyncio
import re
import unicodedata
from playwright.async_api import Page

def normalize_name(text: str) -> str:
    """Remove acentos, converte para minúsculas e remove sufixos comuns de clubes."""
    if not text: return ""
    text = "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    text = text.lower()
    patterns = [
        r"\bclube\b", r"\bfutebol\b", r"\bclub\b", r"\bfc\b", r"\bu\d+\b", r"\bsub-\d+\b",
        r"\bbelediyespor\b", r"\bsf\b", r"\bafc\b", r"\bsc\b", r"\bsp\b", r"\brj\b", r"\bfk\b"
    ]
    for p in patterns:
        text = re.sub(p, "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

class Bet365Scraper:
    BASE_URL = "https://www.bet365.bet.br/"
    async def search_match(self, page: Page, home_team: str, away_team: str):
        """Busca resiliente com estratégiade múltiplas tentativas e verificação cruzada."""
        h_norm = normalize_name(home_team)
        a_norm = normalize_name(away_team)
        
        # Estratégia de termos: [Completo, Apenas Mandante, Apenas Visitante]
        search_terms = [
            f"{home_team} {away_team}",
            home_team.split()[0],
            away_team.split()[0]
        ]

        print(f"    [*] [BET365] Iniciando busca resiliente para: {home_team} vs {away_team}")
        
        try:
            # 1. Garantir Home
            if not page.url.startswith(self.BASE_URL):
                await page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2000)
            
            for term in search_terms:
                if not term or len(term) < 3: continue
                
                print(f"      [>] Tentando termo: '{term}'...")
                
                # 2. Abrir/Limpar Busca
                try:
                    search_btn = await page.wait_for_selector(".sml-SearchBar, .wc-SearchBar", timeout=5000)
                    await search_btn.click()
                except:
                    # Se já estiver aberta, tenta limpar o campo
                    pass
                
                input_field = await page.wait_for_selector("input.sml-SearchTextInput", timeout=5000)
                await input_field.click(click_count=3)
                await page.keyboard.press("Backspace")
                await input_field.fill(term)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(3000)
                
                # 3. Analisar Resultados
                # Seletores tentam capturar os itens de resultado de forma genérica
                results = await page.query_selector_all(".sml-SearchItem, [class*='SearchItem'], .ssm-StaticSearchPaneChild")
                
                for res in results:
                    text = (await res.inner_text()).lower()
                    
                    # Verificação Cruzada: O resultado deve conter fragmentos de AMBOS os times
                    # ou ser uma correspondência muito forte do termo atual
                    h_frag = h_norm.split()[0]
                    a_frag = a_norm.split()[0]
                    
                    if h_frag in text and a_frag in text:
                        print(f"    [+] [BET365] Correspondência confirmada: '{text.splitlines()[0]}'")
                        await res.click()
                        await page.wait_for_timeout(5000)
                        
                        if "#/IP/EV" in page.url:
                            return {"found": True, "url": page.url}
            
            return {"found": False, "url": ""}
        except Exception as e:
            print(f"    [!] [BET365] Erro crítico na busca: {e}")
            return {"found": False, "url": ""}

    async def get_live_stats(self, page: Page):
        """Extrai stats, odds e lista mercados disponíveis usando seletores avançados."""
        stats = {
            "ataques_perigosos": {"home": "0", "away": "0"},
            "remates_alvo": {"home": "0", "away": "0"},
            "escanteios": {"home": "0", "away": "0"},
            "odds": {"home": "N/A", "draw": "N/A", "away": "N/A"},
            "markets_available": [],
            "direct_link": page.url
        }
        try:
            # 1. Ataques Perigosos (Wheel Charts)
            ap_containers = await page.query_selector_all(".ml1-WheelChartAdvanced")
            for container in ap_containers:
                label = await container.query_selector(".ml1-WheelChartAdvanced_Label")
                if label and "Ataques Perigosos" in await label.inner_text():
                    vals = await container.query_selector_all(".ml1-WheelChartAdvanced_Text")
                    if len(vals) >= 2:
                        stats["ataques_perigosos"]["home"] = (await vals[0].inner_text()).strip()
                        stats["ataques_perigosos"]["away"] = (await vals[1].inner_text()).strip()

            # 2. Finalizações / Chutes ao Gol (Progress Bars)
            pb_headers = await page.query_selector_all(".ml1-ProgressBarAdvancedDual_Header")
            for header in pb_headers:
                txt = await header.inner_text()
                if "No Alvo" in txt or "Chutes" in txt:
                    # Encontrar o container pai ou o próximo elemento de valores
                    vals = await header.evaluate_handle("el => el.parentElement.querySelectorAll('.ml1-ProgressBarAdvancedDual_Value')")
                    vals_list = await vals.get_property("length")
                    if vals_list:
                        # Extrair "Total / No Alvo" e pegar só o "No Alvo"
                        v_h = await page.evaluate("el => el.parentElement.querySelectorAll('.ml1-ProgressBarAdvancedDual_Value')[0].innerText", header)
                        v_a = await page.evaluate("el => el.parentElement.querySelectorAll('.ml1-ProgressBarAdvancedDual_Value')[1].innerText", header)
                        
                        # Geralmente formato "4/2"
                        stats["remates_alvo"]["home"] = v_h.split("/")[-1].strip() if "/" in v_h else v_h
                        stats["remates_alvo"]["away"] = v_a.split("/")[-1].strip() if "/" in v_a else v_a

            # 3. Escanteios
            corners_val = await page.query_selector(".ml1-StatWheel_CornerText, .ml1-StatWheel_Stat")
            if corners_val:
                # Na bet365 o carrossel de stats alterna. Tentar pegar do header fixo se existir.
                header_corners = await page.query_selector_all(".ml1-StatsColumn_Stat")
                if len(header_corners) >= 3: # Geralmente Cans, Cartoes, Escanteios
                     # Depende do layout, mas vamos tentar o seletor de gráfico por enquanto
                     pass

            # 4. Odds (Resultado Final)
            market_1x2 = await page.query_selector('.gl-Market_General[data-market-name="Resultado Final"]')
            if market_1x2:
                odds_els = await market_1x2.query_selector_all(".gl-Participant_Odds")
                if len(odds_els) >= 3:
                    stats["odds"]["home"] = (await odds_els[0].inner_text()).strip()
                    stats["odds"]["draw"] = (await odds_els[1].inner_text()).strip()
                    stats["odds"]["away"] = (await odds_els[2].inner_text()).strip()

            # 5. Mercados Disponíveis
            market_groups = await page.query_selector_all(".gl-MarketGroupButton_Text")
            for group in market_groups:
                m_txt = (await group.inner_text()).strip()
                if m_txt and m_txt not in stats["markets_available"]:
                    stats["markets_available"].append(m_txt)

            return stats
        except Exception as e:
            print(f"    [!] [BET365] Erro na extração: {e}")
            return stats
