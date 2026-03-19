"""
dropping_odds_scraper.py — Módulo de Scraping do DroppingOdds.com (v3.0)

Estrutura REAL verificada via browser inspection:
  - Lista live: https://dropping-odds.com/index.php?view=live
  - Linhas de jogos: tr.a_link com atributo game_id="XXXXXXXX"
  - Página base do jogo: https://dropping-odds.com/event.php?id={game_id}
    → Contém link: http://excapper.com/?action=game&id=XXXXXXXX
  - Tabelas de odds por aba URL:
      1X2:      event.php?id={id}&t=1x2
                Colunas: DATE, TIME, SCORE, HOME, DRAW, AWAY, HOME(%), AWAY(%), PENALTY, RED
      Total:    event.php?id={id}&t=total
      Handicap: event.php?id={id}&t=handicap
      HT Total: event.php?id={id}&t=total_ht
      HT 1X2:   event.php?id={id}&t=1x2_ht
  - Container: div.tablediv > table (tabela única sem classes)
  - Drop %: colunas HOME (%) e AWAY (%) como strings "-5%", "7%"
"""

import asyncio
import re
from typing import List, Dict, Optional
from playwright.async_api import Page

# ─── Constantes ────────────────────────────────────────────────────────────────
BASE_URL  = "https://dropping-odds.com"
LIVE_URL  = "https://dropping-odds.com/index.php?view=live"

from ..config import DROP_MIN_PCT, DROP_STRONG_PCT, DROP_ALERT_PCT

# Mapeamento nome → parâmetro URL
TABLE_TABS = {
    "1X2":      "1x2",
    "Total":    "total",
    "Handicap": "handicap",
    "HT Total": "total_ht",
    "HT 1X2":   "1x2_ht",
}

# Índices das colunas por mercado (baseado na estrutura real observada)
# 1X2: DATE(0) TIME(1) SCORE(2) HOME(3) DRAW(4) AWAY(5) HOME%(6) AWAY%(7) PENALTY(8) RED(9)
# Total/HT: DATE(0) TIME(1) SCORE(2) OVER(3) UNDER(4) CHANGE%(5) [ou similar]
TABLE_PCT_COL_HINTS = {
    "1X2":      ["home (%)", "away (%)", "draw (%)", "%"],
    "Total":    ["drop", "%", "over (%)", "under (%)"],
    "Handicap": ["drop", "sharpness", "%"],
    "HT Total": ["drop", "%", "over (%)", "under (%)"],
    "HT 1X2":   ["home (%)", "away (%)", "draw (%)", "%"],
}


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _parse_pct(text: str) -> float:
    """Extrai valor absoluto de porcentagem de '-12.5%' → 12.5."""
    text = str(text).strip()
    try:
        cleaned = re.sub(r"[^0-9.\-,]", "", text).replace(",", ".")
        return abs(float(cleaned)) if cleaned and cleaned != "-" else 0.0
    except (ValueError, AttributeError):
        return 0.0


def _parse_odd(text: str) -> float:
    """Extrai valor de odd de texto, retorna 0 se inválido."""
    try:
        cleaned = re.sub(r"[^0-9.,]", "", str(text)).replace(",", ".")
        v = float(cleaned) if cleaned else 0.0
        return v if 1.001 < v < 1000.0 else 0.0
    except (ValueError, AttributeError):
        return 0.0


def _is_pct_col(header: str) -> bool:
    """Verifica se um header de coluna indica percentagem de mudança."""
    h = header.lower().strip()
    return "%" in h or "drop" in h or "change" in h or "sharpness" in h


def _drop_severity(drop_pct: float) -> str:
    if drop_pct >= DROP_ALERT_PCT:
        return "🔴 CRÍTICO"
    elif drop_pct >= DROP_STRONG_PCT:
        return "🟠 FORTE"
    return "🟡 MODERADO"


# ─── Classe Principal ──────────────────────────────────────────────────────────

class DroppingOddsScraper:
    """Scraper para dropping-odds.com com seletores verificados via browser inspection."""

    async def get_live_matches(self, page: Page) -> List[Dict]:
        """
        Extrai lista de jogos ao vivo da página principal.
        Usa seletor verificado: tr.a_link com atributo game_id.

        Retorna lista de:
        {
            "game_id": str,
            "teams": str,
            "league": str,
            "score": str,
            "time_text": str,
            "is_live": bool,
            "match_url": str,
        }
        """
        matches = []
        try:
            print("[*] [DO] Acessando lista live...")
            await page.goto(LIVE_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)

            rows = await page.query_selector_all("tr.a_link")
            print(f"[*] [DO] {len(rows)} linhas encontradas (tr.a_link).")

            for row in rows:
                try:
                    game_id = await row.get_attribute("game_id")
                    if not game_id:
                        continue

                    cols = await row.query_selector_all("td")
                    col_texts = []
                    for col in cols:
                        col_texts.append((await col.inner_text()).strip())

                    # Texto completo da linha
                    full_text = " ".join(col_texts)

                    # Extrair time/placar (ex: "0-0", "1:2")
                    score_m = re.search(r"\b(\d)\s*[-:]\s*(\d)\b", full_text)
                    score = f"{score_m.group(1)}-{score_m.group(2)}" if score_m else ""

                    # Tempo do jogo
                    time_text = col_texts[0] if col_texts else ""

                    # É live? (tem minuto como "35'" ou "HT" ou placar)
                    is_live = bool(
                        re.search(r"\d+['\"]", time_text) or
                        "HT" in time_text.upper() or
                        (score and "." not in time_text)  # tem placar e não é data
                    )

                    # Liga (tipicamente 2ª coluna)
                    league = col_texts[1] if len(col_texts) > 1 else ""

                    # Times: buscar link de evento ou coluna com texto de times
                    teams_text = ""
                    link_el = await row.query_selector("a")
                    if link_el:
                        teams_text = (await link_el.inner_text()).strip()

                    if not teams_text:
                        # Procurar texto não-numérico nas colunas do meio
                        for ct in col_texts[2:6]:
                            if ct and len(ct) > 3 and not re.match(r'^[\d\s%\-+:.,:/()\[\]]+$', ct):
                                teams_text = ct
                                break

                    if not teams_text:
                        teams_text = f"Jogo {game_id}"

                    match_url = f"{BASE_URL}/event.php?id={game_id}"
                    matches.append({
                        "game_id":   game_id,
                        "teams":     teams_text,
                        "league":    league,
                        "score":     score,
                        "time_text": time_text,
                        "is_live":   is_live,
                        "match_url": match_url,
                    })

                    status = "LIVE" if is_live else "PRÉ"
                    print(f"    [{status}] ID:{game_id} | {teams_text[:40]}")

                except Exception:
                    continue

        except Exception as e:
            print(f"[!] [DO] Erro ao listar jogos: {e}")

        return matches

    async def get_match_full_data(self, page: Page, game_id: str) -> Dict:
        """
        Para um jogo específico:
        1. Acessa evento base → extrai link Excapper
        2. Acessa cada aba (1X2, Total, Handicap, HT Total, HT 1X2) → extrai drops

        Retorna:
        {
            "excapper_url": str | None,
            "tables": { "1X2": [...], "Total": [...], ... },
            "drops_summary": [
                {"table": str, "selection": str, "open_odd": float,
                 "current_odd": float, "drop_pct": float, "severity": str}
            ],
            "has_drops": bool,
            "max_drop_pct": float,
        }
        """
        result = {
            "excapper_url":  None,
            "tables":        {},
            "drops_summary": [],
            "has_drops":     False,
            "max_drop_pct":  0.0,
        }

        # ── 1. Página base: extrai link Excapper ─────────────────────────────
        base_url = f"{BASE_URL}/event.php?id={game_id}"
        try:
            await page.goto(base_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)
            result["excapper_url"] = await self._find_excapper_link(page)
            if result["excapper_url"]:
                print(f"  [✓] Excapper: {result['excapper_url']}")
            else:
                print(f"  [?] Sem link Excapper para game {game_id}.")
        except Exception as e:
            print(f"  [!] Erro na página base do jogo {game_id}: {e}")

        # ── 2. Cada aba de odds ──────────────────────────────────────────────
        all_drops = []
        for table_name, tab_param in TABLE_TABS.items():
            try:
                tab_url = f"{BASE_URL}/event.php?id={game_id}&t={tab_param}"
                await page.goto(tab_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                rows_data = await self._extract_table_rows(page, table_name)
                if rows_data:
                    result["tables"][table_name] = rows_data
                    drops_in_tab = [r for r in rows_data if r["drop_pct"] >= DROP_MIN_PCT]
                    print(f"  [+] [{table_name}] {len(rows_data)} linhas | {len(drops_in_tab)} drops ≥{DROP_MIN_PCT}%")
                    for row in drops_in_tab:
                        all_drops.append({
                            "table":       table_name,
                            "selection":   row["selection"],
                            "open_odd":    row.get("open_odd", 0.0),
                            "current_odd": row.get("current_odd", 0.0),
                            "drop_pct":    row["drop_pct"],
                            "severity":    _drop_severity(row["drop_pct"]),
                        })
                else:
                    print(f"  [-] [{table_name}] Sem dados.")

            except Exception as e:
                print(f"  [!] Erro em [{table_name}]: {e}")

        # Ordenar por severidade
        all_drops.sort(key=lambda x: x["drop_pct"], reverse=True)
        result["drops_summary"] = all_drops
        result["has_drops"]     = len(all_drops) > 0
        result["max_drop_pct"]  = all_drops[0]["drop_pct"] if all_drops else 0.0

        return result

    async def _find_excapper_link(self, page: Page) -> Optional[str]:
        """Procura link do Excapper usando seletor verificado."""
        try:
            links = await page.query_selector_all("a[href*='excapper.com']")
            for link in links:
                href = await link.get_attribute("href")
                if href:
                    return href.strip()

            # Fallback via regex no HTML da página
            content = await page.content()
            found = re.findall(r'https?://(?:www\.)?excapper\.com[^\s"\'<>]*', content)
            if found:
                return found[0]
        except Exception:
            pass
        return None

    async def _extract_table_rows(self, page: Page, table_name: str) -> List[Dict]:
        """
        Extrai drops de odds e anomalias baseadas em classes (Red1, Red2, Red3)
        e eventos (Penalty, Red Card).
        """
        rows_data = []
        try:
            table = await page.query_selector("div.tablediv table")
            if not table:
                table = await page.query_selector("table")
            if not table:
                return rows_data

            # ── Ler headers para identificar colunas ────────────────────────
            headers = []
            header_row = await table.query_selector("thead tr, tr:first-child")
            if header_row:
                header_cells = await header_row.query_selector_all("th, td")
                headers = [(await c.inner_text()).strip() for c in header_cells]

            # Mapear índices
            odd_col_map = {}
            pct_col_map = {}
            score_idx = -1
            penalty_idx = -1
            red_card_idx = -1

            for i, h in enumerate(headers):
                hl = h.lower().strip()
                if "score" in hl: score_idx = i
                elif "home (%)" in hl or "home(%)" in hl: pct_col_map["Home"] = i
                elif "away (%)" in hl or "away(%)" in hl: pct_col_map["Away"] = i
                elif "draw (%)" in hl or "draw(%)" in hl: pct_col_map["Draw"] = i
                elif "over (%)" in hl or "over(%)" in hl: pct_col_map["Over"] = i
                elif "under (%)" in hl or "under(%)" in hl: pct_col_map["Under"] = i
                elif hl == "home": odd_col_map["Home"] = i
                elif hl == "draw": odd_col_map["Draw"] = i
                elif hl == "away": odd_col_map["Away"] = i
                elif hl == "over": odd_col_map["Over"] = i
                elif hl == "under": odd_col_map["Under"] = i
                elif hl == "handicap": odd_col_map["Handicap"] = i
                elif "penalty" in hl: penalty_idx = i
                elif "red" in hl: red_card_idx = i
                elif "drop" in hl or "sharp" in hl or "change" in hl:
                    key = {"Total": "Over/Under", "HT Total": "Over/Under", "Handicap": "Handicap"}.get(table_name, "Principal")
                    pct_col_map[key] = i

            # ── Ler linhas buscando classes e ícones ────────────────────────
            data_rows = await table.query_selector_all("tbody tr")
            if not data_rows:
                all_rows = await table.query_selector_all("tr")
                data_rows = all_rows[1:] if len(all_rows) > 1 else []

            all_row_data = []
            for tr in data_rows:
                tds = await tr.query_selector_all("td")
                if not tds: continue
                
                texts = []
                has_penalty = False
                has_red_card = False

                for i, td in enumerate(tds):
                    txt = (await td.inner_text()).strip()
                    texts.append(txt)
                    # Verificar ícones em colunas específicas
                    if i == penalty_idx or i == red_card_idx:
                        inner_html = await td.inner_html()
                        if "img" in inner_html.lower() or "icon" in inner_html.lower():
                            if i == penalty_idx: has_penalty = True
                            if i == red_card_idx: has_red_card = True
                
                row_class = await tr.get_attribute("class") or ""
                # DroppingOdds costuma marcar TDs com Red1/2/3 quando o drop ocorre ali
                td_classes = []
                for td in tds:
                    c = await td.get_attribute("class") or ""
                    if any(x in c for x in ["Red1", "Red2", "Red3"]):
                        td_classes.append(c)

                if any(texts):
                    all_row_data.append({
                        "texts": texts,
                        "class": row_class,
                        "td_classes": td_classes,
                        "has_penalty": has_penalty,
                        "has_red_card": has_red_card
                    })

            if not all_row_data:
                return rows_data

            # ── Histórico e Cálculo de Drops ─────────────────────────────────
            # Usar a primeira linha como atual e a última como abertura
            first_row_item = all_row_data[0]
            first_row      = first_row_item["texts"]
            last_row       = all_row_data[-1]["texts"]

            # Anomalias de Classe (Red2, Red3 são prioritárias)
            # Scan em todas as linhas para ver se houve sinal crítico em algum momento
            anomaly_signals = []
            for item in all_row_data:
                combined_cls = item["class"] + " " + " ".join(item["td_classes"])
                if "Red3" in combined_cls: anomaly_signals.append("CRITICAL_DROP_RED3")
                elif "Red2" in combined_cls: anomaly_signals.append("STRONG_DROP_RED2")
                
                if item["has_penalty"]: anomaly_signals.append("PENALTY_EVENT")
                if item["has_red_card"]: anomaly_signals.append("RED_CARD_EVENT")

            # Cálculo por seleções
            if pct_col_map:
                for sel_name, pct_idx in pct_col_map.items():
                    if pct_idx >= len(first_row): continue
                    drop_pct = _parse_pct(first_row[pct_idx])
                    
                    current_odd = _parse_odd(first_row[odd_col_map[sel_name]]) if sel_name in odd_col_map else 0.0
                    open_odd    = _parse_odd(last_row[odd_col_map[sel_name]]) if sel_name in odd_col_map else 0.0

                    rows_data.append({
                        "selection":   sel_name,
                        "open_odd":    open_odd,
                        "current_odd": current_odd,
                        "drop_pct":    drop_pct,
                        "score":       first_row[score_idx] if score_idx >= 0 else "",
                        "signals":     list(set(anomaly_signals)), # Eventos detectados no histórico
                    })

            elif odd_col_map:
                for sel_name, oc in odd_col_map.items():
                    if oc >= len(first_row) or oc >= len(last_row): continue
                    curr = _parse_odd(first_row[oc])
                    orig = _parse_odd(last_row[oc])
                    if orig > 0 and curr > 0:
                        drop_pct = round(((orig - curr) / orig * 100), 2)
                        rows_data.append({
                            "selection":   sel_name,
                            "open_odd":    orig,
                            "current_odd": curr,
                            "drop_pct":    drop_pct,
                            "score":       first_row[score_idx] if score_idx >= 0 else "",
                            "signals":     list(set(anomaly_signals)),
                        })

        except Exception as e:
            print(f"    [!] Erro ao extrair [{table_name}]: {e}")

        return rows_data


    def _infer_selection_for_pct(
        self, headers: List[str], pct_idx: int, row_texts: List[str], table_name: str
    ) -> str:
        """Tenta inferir o nome da seleção (Home/Away/Over/Under/etc.) para um % de drop."""
        # 1. Usar header da coluna de % como hint
        if pct_idx < len(headers):
            h = headers[pct_idx].strip()
            # Ex: "Home (%)" → "Home"
            m = re.match(r"^\s*([A-Za-z\s/]+)\s*\(%\)", h)
            if m:
                return m.group(1).strip()
            # Ex: "Drop" com contexto de mercado Total → "Over" ou "Under"
            if "drop" in h.lower() and table_name in ("Total", "HT Total"):
                return "Over/Under"

        # 2. Tentar coluna anterior (odd correspondente)
        if pct_idx > 0 and (pct_idx - 1) < len(headers):
            prev_header = headers[pct_idx - 1].strip()
            if prev_header and not _is_pct_col(prev_header):
                return prev_header

        # 3. Fallback por tipo de mercado
        fallbacks = {
            "1X2":      {6: "Home", 7: "Away"},
            "HT 1X2":   {6: "Home", 7: "Away"},
            "Total":    {5: "Over/Under"},
            "HT Total": {5: "Over/Under"},
            "Handicap": {5: "Handicap"},
        }
        fb = fallbacks.get(table_name, {})
        if pct_idx in fb:
            return fb[pct_idx]

        return f"Sel-{pct_idx}"

    def format_drops_for_ai(self, match: Dict, match_data: Dict) -> str:
        """Formata dados de drops para o contexto de análise da IA."""
        lines = []
        lines.append(f"ANÁLISE DE DROPS — {match.get('teams', 'N/A')}")
        lines.append(f"Liga: {match.get('league', 'N/A')}")
        lines.append(f"Placar: {match.get('score', 'N/A')} | Tempo: {match.get('time_text', 'N/A')}")
        lines.append("")
        lines.append("DROPS IDENTIFICADOS NAS TABELAS:")

        drops = match_data.get("drops_summary", [])
        if drops:
            for drop in drops:
                lines.append(
                    f"  • [{drop['table']}] {drop['selection']} → "
                    f"Odd Atual: {drop['current_odd']:.2f} | "
                    f"Queda: -{drop['drop_pct']:.1f}% {drop['severity']}"
                )
        else:
            lines.append("  • Nenhum drop significativo detectado.")

        exc_url = match_data.get("excapper_url")
        lines.append("")
        lines.append(f"LINK EXCAPPER: {exc_url or 'Não disponível'}")

        return "\n".join(lines)
