import asyncio
import re
import unicodedata
from playwright.async_api import Page

def normalize_name(text: str) -> str:
    """Remove acentos, converte para minúsculas e remove sufixos comuns de clubes."""
    if not text: return ""
    # Remover acentos (Ç -> C, etc.)
    text = "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    text = text.lower()
    # Remover sufixos e termos comuns
    patterns = [
        r"\bclube\b", r"\bfutebol\b", r"\bclub\b", r"\bfc\b", r"\bu\d+\b", r"\bsub-\d+\b",
        r"\bbelediyespor\b", r"\bsf\b", r"\bafc\b", r"\bsc\b", r"\bsp\b", r"\brj\b", r"\bfk\b"
    ]
    for p in patterns:
        text = re.sub(p, "", text)
    # Limpar espaços extras
    text = re.sub(r"\s+", " ", text).strip()
    return text

class SofaScorePreLiveScraper:
    BASE_URL = "https://www.sofascore.com/pt/"

    async def search_match(self, page: Page, home_team: str, away_team: str):
        """Procura o jogo no SofaScore de forma resiliente."""
        h_norm = normalize_name(home_team)
        a_norm = normalize_name(away_team)
        
        search_query = f"{h_norm.split()[0]} {a_norm.split()[0]}"
        print(f"    [*] [SOFASCORE] Buscando: {search_query}")
        
        try:
            await page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=45000)
            
            # Selector atualizado via pesquisa
            search_input = await page.wait_for_selector('#search-input', timeout=10000)
            await search_input.fill(search_query)
            await page.keyboard.press("Enter")
            
            await page.wait_for_timeout(4000)
            # Link da partida nos resultados (Dropdown ou Página de busca)
            links = await page.query_selector_all('a[href*="/match/"]')
            
            for link in links:
                href = await link.get_attribute("href")
                inner_text = await link.inner_text()
                t_norm = normalize_name(inner_text)
                
                if h_norm.split()[0] in t_norm and a_norm.split()[0] in t_norm:
                    print(f"    [+] [SOFASCORE] Partida encontrada: {inner_text}")
                    return {"url": f"https://www.sofascore.com{href}"}
            
            return None
        except Exception as e:
            print(f"    [!] [SOFASCORE] Erro na busca: {e}")
            return None

    async def get_prelive_data(self, page: Page, match_url: str):
        """Extrai H2H, Forma e Séries usando seletores de componentes (Cards)."""
        data = {"h2h": "", "form": {"home": "", "away": ""}, "streaks": []}
        try:
            await page.goto(match_url, wait_until="domcontentloaded", timeout=45000)
            
            # 1. Navegar para Aba Partidas/H2H (Selector: div#tabpanel-matches)
            # Tentar clicar no botão H2H se disponível
            h2h_btn = await page.query_selector('button:has-text("H2H"), a[href*="tab:matches"]')
            if h2h_btn:
                await h2h_btn.click()
                await page.wait_for_timeout(3000)

            # 2. Localizar Container H2H
            h2h_panel = await page.query_selector("div#tabpanel-matches")
            if not h2h_panel:
                h2h_panel = page # Fallback para a pagina toda se o ID mudou

            # 3. Extrair Séries e Sequências (Cards)
            # Headers comuns: "Sequências", "Séries confrontos diretos", "Estatísticas da equipe"
            cards = await h2h_panel.query_selector_all("div.card-component")
            
            for card in cards:
                header = await card.query_selector("h3, span[class*='Text']")
                header_text = (await header.inner_text()).strip() if header else ""
                
                if any(x in header_text for x in ["Sequências", "Séries", "Match facts", "Team streaks"]):
                    rows = await card.query_selector_all("div.p_sm > div")
                    for row in rows:
                        txt = (await row.inner_text()).strip().replace("\n", ": ")
                        if txt and ":" in txt:
                            data["streaks"].append(txt)
                
                # H2H Summary (Se houver texto corrido num card)
                if "Confrontos diretos" in header_text or "Head2head" in header_text:
                    summary = await card.query_selector("div.p_sm")
                    if summary:
                        data["h2h"] = (await summary.inner_text()).replace("\n", " ").strip()

            # 4. Forma (Icons) - Fallback extração de spans coloridos
            if not data["form"]["home"]:
                sections = await page.query_selector_all("div[class*='sc-bc6048d0'], div:has(> span[class*='sc-e81816e8'])")
                if len(sections) >= 2:
                    for i, section in enumerate(sections[:2]):
                        icons = await section.query_selector_all("span")
                        res = []
                        for ic in icons:
                            t = (await ic.inner_text()).strip()
                            if t in ["V", "E", "D", "W", "D", "L"]: res.append(t)
                        data["form"]["home" if i==0 else "away"] = "".join(res[:5])

            # Validação: Se pegou ao menos 1 streak ou H2H, consideramos sucesso
            return data if (data["h2h"] or data["streaks"]) else None
        except Exception as e:
            print(f"    [!] [SOFASCORE] Erro na extração aprofundada: {e}")
            return None
