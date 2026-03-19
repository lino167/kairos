"""
main_dropping.py — Pipeline Principal: DroppingOdds → Excapper → IA (v1.0)

Fluxo completo:
  1. Acessa dropping-odds.com e lista jogos ao vivo
  2. Para cada jogo, navega até a página individual e extrai drops das tabelas
     (1X2, Total, Handicap, HT Total, HT 1X2)
  3. Se encontrar link Excapper na página, extrai o fluxo de dinheiro
  4. Envia TODOS os dados para a IA (Gemini/DeepSeek) analisar
  5. Gera e envia alerta profissional no Telegram

Uso: python -m src.main_dropping
"""

import asyncio
import json
import os
import re
import time
import hashlib
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from .utils import load_json, save_json, send_telegram_alert
from .analyzer import KairosAnalyzer
from .excapper_scraper import ExcapperScraper
from .dropping_odds_scraper import DroppingOddsScraper, DROP_MIN_PCT, DROP_STRONG_PCT, DROP_ALERT_PCT
from .smart_money import run_smart_money_analysis, TIER_ICON

# ── Configuração ───────────────────────────────────────────────────────────────
load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")
AI_PROVIDER      = os.getenv("AI_PROVIDER", "gemini")

DATA_DIR          = "data"
SENT_ALERTS_FILE  = os.path.join(DATA_DIR, "sent_alerts_dropping.json")

# Ciclo de monitoramento (segundos)
CYCLE_SLEEP_SEC = 90

# Limiares de drop mínimo para acionar análise de Excapper e IA
EXCAPPER_TRIGGER_DROP  = DROP_STRONG_PCT   # 10%+ aciona busca no Excapper
AI_TRIGGER_DROP        = DROP_MIN_PCT      # 5%+ (qualquer drop vai para IA se tiver Excapper)


# ── Funções Auxiliares ─────────────────────────────────────────────────────────

def _build_ai_snapshot(
    match: dict,
    page_data: dict,
    excapper_markets: dict,
    teams: str,
) -> dict:
    """
    Monta o snapshot completo para análise da IA combinando dados de:
    - DroppingOdds (drops por tabela)
    - Excapper (fluxo de dinheiro por mercado)
    """
    drops = page_data.get("drops_summary", [])
    excapper_url = page_data.get("excapper_url")

    # Selecionar o drop principal (maior severidade)
    primary_drop = drops[0] if drops else {}

    # Montar fluxo do Excapper para o mercado com maior drop
    primary_market_flow = []
    primary_market_name = primary_drop.get("table", "")
    excapper_primary = {}

    # Mapear tabelas do DroppingOdds para nomes do Excapper
    table_to_excapper = {
        "1X2":      ["Match Odds", "Match Result"],
        "Total":    ["Over/Under 2.5 Goals", "Over/Under 1.5 Goals", "Over/Under 3.5 Goals"],
        "Handicap": ["Asian Handicap"],
        "HT Total": ["First Half Goals 1.5", "First Half Goals 0.5"],
        "HT 1X2":   ["Half Time"],
    }

    if excapper_markets:
        # Busca o mercado correspondente no Excapper
        possible_names = table_to_excapper.get(primary_market_name, [])
        for pname in possible_names:
            if pname in excapper_markets:
                excapper_primary = excapper_markets[pname]
                primary_market_flow = excapper_primary.get("flow", [])
                break

        # Se não achou, pega o primeiro mercado disponível com flow
        if not primary_market_flow:
            for mname, mdata in excapper_markets.items():
                if mdata.get("flow"):
                    primary_market_flow = mdata["flow"]
                    excapper_primary = mdata
                    primary_market_name = mname
                    break

    snapshot = {
        "match_name":     teams,
        "live_score":     match.get("score", "N/A"),
        "is_live":        match.get("is_live", False),
        "current_minute": _extract_minute(match.get("time_text", "0")),
        "league":         match.get("league", ""),
        "excapper_url":   excapper_url,

        # Drops do DroppingOdds
        "dropping_odds_drops": drops,
        "primary_drop": primary_drop,

        # Dados do Excapper (fluxo de dinheiro)
        "excapper_markets": {
            k: {"flow": v.get("flow", [])[:10], "betfair_url": v.get("betfair_url", "")}
            for k, v in (excapper_markets or {}).items()
        },
        "primary_excapper_flow": primary_market_flow[:10],
        "primary_excapper_market": primary_market_name,

        # Contexto estratégico (compatibilidade com analyzer.py)
        "primary_anomaly": {
            "market":    primary_drop.get("table", "N/A"),
            "selection": primary_drop.get("selection", "N/A"),
            "reason":    f"Drop {primary_drop.get('drop_pct', 0):.1f}% em {primary_drop.get('table', '')}",
            "short_id":  f"{primary_drop.get('table', '')}_{primary_drop.get('selection', '')}",
            "bf_url":    excapper_primary.get("betfair_url", "https://www.betfair.com"),
            "details": {
                "change_eur": primary_market_flow[0].get("change_eur", 0) if primary_market_flow else 0,
                "change_pct": f"-{primary_drop.get('drop_pct', 0):.1f}%",
                "odds":       primary_drop.get("current_odd", 0),
                "score":      match.get("score", ""),
            }
        },
        "all_anomalies": [
            {
                "market":    d.get("table", "N/A"),
                "selection": d.get("selection", "N/A"),
                "reason":    f"Drop {d.get('drop_pct', 0):.1f}% em {d.get('table', '')}",
                "short_id":  f"{d.get('table', '')}_{d.get('selection', '')}",
                "bf_url":    "https://www.betfair.com",
                "details": {
                    "change_eur": 0,
                    "change_pct": f"-{d.get('drop_pct', 0):.1f}%",
                    "odds":       d.get("current_odd", 0),
                    "score":      match.get("score", ""),
                }
            }
            for d in drops
        ],

        # Compatibilidade analyzer.py
        "sokkerpro_live": None,
        "sokkerpro_pre":  None,
        "smart_money_result": {
            "league_profile": {"tier": "MID", "spark_threshold": 1000, "disp_threshold": 400},
            "tier_icon": "🏞️",
            "signals": [],
            "safety_filtered": False,
            "filter_reasons": [],
            "summary_label": "Análise via DroppingOdds",
        },
        "strategic_context": {
            "is_ocean": False,
            "avg_appm": 0,
            "is_divergence": False,
            "manipulation_labels": [
                f"DROP_{d['table'].upper().replace(' ', '_')}_{d['drop_pct']:.0f}PCT {d['severity']}"
                for d in drops[:4]
            ],
        },
    }

    # Tentar rodar Smart Money se tiver fluxo do Excapper
    if primary_market_flow:
        try:
            sm_result = run_smart_money_analysis(
                flow_history=primary_market_flow,
                league_name=match.get("league", ""),
                current_minute=snapshot["current_minute"],
                is_halftime=("HT" in str(match.get("time_text", "")).upper()),
                current_odd=float(primary_drop.get("current_odd", 0) or 0),
                primary_change_eur=float(primary_market_flow[0].get("change_eur", 0)),
                market_name=primary_market_name,
            )
            snapshot["smart_money_result"] = sm_result
            snapshot["strategic_context"]["is_ocean"] = (
                sm_result["league_profile"]["tier"] == "OCEAN"
            )
        except Exception as ex:
            print(f"    [!] Smart Money falhou: {ex}")

    return snapshot


def _extract_minute(time_text: str) -> int:
    """Extrai minuto de um texto como '73\'' → 73."""
    try:
        m = re.search(r"\d+", str(time_text))
        return int(m.group()) if m else 0
    except Exception:
        return 0


def _build_telegram_message(
    match: dict,
    page_data: dict,
    ai_data: dict,
    snapshot: dict,
) -> str:
    """Monta a mensagem Telegram completa com dados do DroppingOdds + Excapper + IA."""
    teams      = match.get("teams", "N/A")
    league     = match.get("league", "Futebol")
    score      = match.get("score", "")
    time_text  = match.get("time_text", "")
    is_live    = match.get("is_live", False)
    drops      = page_data.get("drops_summary", [])
    exc_url    = page_data.get("excapper_url", "")
    do_url     = match.get("match_url", "https://dropping-odds.com")

    sm = snapshot.get("smart_money_result", {})
    sm_tier_icon  = sm.get("tier_icon", "🏞️")
    sm_tier_label = sm.get("league_profile", {}).get("tier", "MID")
    sm_signals    = sm.get("signals", [])

    # Confiança e estrelas
    try:
        conf_val = int(ai_data.get("confidence", 5))
    except (ValueError, TypeError):
        conf_val = 5
    conf_val = max(1, min(10, conf_val))
    stars    = "⭐" * (conf_val // 2 if conf_val > 1 else 1)

    # Verdict icon
    verdict_map = {
        "SHARP_ACTION":       "🎯 SHARP ACTION",
        "INSTITUTIONAL_FLOW": "🏦 INSTITUTIONAL FLOW",
        "SUSPICIOUS":         "🚨 SUSPICIOUS",
        "NOISE":              "📉 NOISE",
    }
    verdict_str = verdict_map.get(
        str(ai_data.get("verdict", "")).upper(),
        f"🔍 {ai_data.get('verdict', 'N/A')}"
    )

    # Headline
    headline = ai_data.get("alert_headline") or f"Drop detectado em {teams}"
    if len(headline) > 90:
        headline = headline[:87] + "…"

    # Stake badge
    stake_raw = str(ai_data.get("stake_suggestion", "Mínimo")).lower()
    if "alto" in stake_raw:
        stake_badge = "🟢 ALTO"
    elif "normal" in stake_raw or "médio" in stake_raw or "medio" in stake_raw:
        stake_badge = "🟡 NORMAL"
    else:
        stake_badge = "🔴 MÍNIMO"

    # ── Montar mensagem ──────────────────────────────────────────────────────
    msg = (
        f"🛰️ <b>KAIROS INTELLIGENCE</b> — <code>DroppingOdds v1.0</code>\n"
        f"{'━' * 28}\n"
        f"<b>📣 {headline}</b>\n"
        f"{'━' * 28}\n\n"
        f"🏆 <b>Liga:</b> {league}  {sm_tier_icon} <code>[{sm_tier_label}]</code>\n"
        f"⚽ <b>Partida:</b> {teams}\n"
    )

    if is_live:
        msg += f"🔴 <b>Live:</b> <code>{score}</code>  ⏱ <code>{time_text}</code>\n"
    else:
        msg += f"🔵 <b>Horário:</b> <code>{time_text}</code>\n"

    msg += f'🔗 <a href="{do_url}">Ver no DroppingOdds</a>\n'
    if exc_url:
        msg += f'🔗 <a href="{exc_url}">Ver no Excapper</a>\n'

    # Drops detectados
    msg += f"\n{'─' * 28}\n"
    msg += "📉 <b>DROPS DE ODDS DETECTADOS:</b>\n"
    if drops:
        for drop in drops[:6]:  # Máx 6 drops no alerta
            sev_icon = "🔴" if "CRÍTICO" in drop["severity"] else ("🟠" if "FORTE" in drop["severity"] else "🟡")
            msg += (
                f"  {sev_icon} <code>[{drop['table']}]</code> "
                f"<b>{drop['selection']}</b> → "
                f"Abertura: {drop['open_odd']:.2f} | Atual: {drop['current_odd']:.2f} | "
                f"<b>-{drop['drop_pct']:.1f}%</b>\n"
            )
    else:
        msg += "  • N/A\n"

    # Fluxo Excapper (se disponível)
    exc_markets = snapshot.get("excapper_markets", {})
    if exc_markets:
        msg += f"\n{'─' * 28}\n"
        msg += "💰 <b>FLUXO DE DINHEIRO (Excapper):</b>\n"
        for mname, mdata in list(exc_markets.items())[:3]:  # Máx 3 mercados
            flow = mdata.get("flow", [])
            if flow:
                recent = flow[0]
                msg += (
                    f"  • <code>{mname}</code>: "
                    f"{recent.get('change_eur', 0):.0f}€ → "
                    f"Odd {recent.get('odds', 'N/A')} ({recent.get('change_pct', 'N/A')})\n"
                )

    # Smart Money Signals
    if sm_signals:
        msg += f"\n{'─' * 28}\n"
        msg += "🔬 <b>SMART MONEY SIGNALS:</b>\n"
        for sig in sm_signals:
            msg += f"  ├ <code>{sig['label']}</code>: {sig.get('description', '')}\n"

    # Análise IA
    msg += (
        f"\n{'─' * 28}\n"
        f"🧠 <b>VEREDITO IA:</b>  {verdict_str}\n"
        f"📌 <b>Análise:</b> {ai_data.get('reasoning', 'N/A')}\n\n"
        f"{'─' * 28}\n"
        f"💰 <b>APOSTA:</b>  <code>{str(ai_data.get('betting_tip', 'N/A')).upper()}</code>\n"
        f"🎯 <b>Odd Mín.:</b> <code>{ai_data.get('suggested_odd', 'Live')}</code>  "
        f"📊 <b>Stake:</b> {stake_badge}\n"
        f"⭐ <b>Confiança:</b> {conf_val}/10  {stars}\n"
        f"⚠️ <b>Risco:</b> {ai_data.get('risk', 'Médio')}\n"
    )

    # Betfair link (do Excapper se disponível)
    primary = snapshot.get("primary_anomaly", {})
    bf_url = primary.get("bf_url", "https://www.betfair.com")
    msg += (
        f"\n{'━' * 28}\n"
        f'🔗 <a href="{bf_url}">⚡ ABRIR NA BETFAIR</a>'
    )

    return msg


# ── Pipeline Principal ─────────────────────────────────────────────────────────

async def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    sent_alerts = load_json(SENT_ALERTS_FILE)

    analyzer  = KairosAnalyzer(GEMINI_API_KEY, provider_type=AI_PROVIDER)
    do_scraper  = DroppingOddsScraper()
    exc_scraper = ExcapperScraper()

    print("\n==================================================")
    print("🚀 KAIROS DROPPING-ODDS: Monitoramento Ativo")
    print(f"   Provedor IA: {AI_PROVIDER.upper()}")
    print(f"   Gatilho Drop: ≥{AI_TRIGGER_DROP}% → Análise | ≥{EXCAPPER_TRIGGER_DROP}% → Excapper")
    print(f"   Ciclo: {CYCLE_SLEEP_SEC}s")
    print("==================================================\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
        )

        main_page = await context.new_page()

        while True:
            if main_page.is_closed():
                print("[!] Página principal fechada. Recriando...")
                main_page = await context.new_page()

            try:
                print(f"\n[{time.strftime('%H:%M:%S')}] ═══ NOVO CICLO ═══")

                # ── FASE 1: DroppingOdds — lista de jogos ao vivo ────────────
                live_matches = await do_scraper.get_live_matches(main_page)
                print(f"[*] {len(live_matches)} jogos ao vivo encontrados.")

                for match in live_matches:
                    teams    = match["teams"]

                    print(f"\n  [{time.strftime('%H:%M:%S')}] Processando: {teams}...")

                    # ── FASE 2: Dados completos do jogo (todas as tabelas + Excapper link) ─
                    game_id = match.get("game_id", "")
                    if not game_id:
                        print(f"    [?] Sem game_id para {teams}. Pulando.")
                        continue

                    game_page = await context.new_page()
                    try:
                        page_data = await do_scraper.get_match_full_data(game_page, game_id)
                    finally:
                        await game_page.close()

                    drops = page_data.get("drops_summary", [])
                    max_drop = page_data.get("max_drop_pct", 0)
                    if not drops:
                        print(f"    [?] Nenhum drop encontrado para {teams}. Pulando.")
                        continue
                    print(f"    [!] {len(drops)} drops detectados | Máx: {max_drop:.1f}%")

                    excapper_url = page_data.get("excapper_url")

                    # ── FASE 3: Excapper — fluxo de dinheiro (se link disponível e drop forte) ──
                    excapper_markets = {}
                    if excapper_url and max_drop >= EXCAPPER_TRIGGER_DROP:
                        print(f"    [*] Extraindo fluxo Excapper (drop {max_drop:.1f}% ≥ {EXCAPPER_TRIGGER_DROP}%)...")
                        m_exc = re.search(r"id=(\d+)", excapper_url)
                        if m_exc:
                            exc_game_id = m_exc.group(1)
                            exc_page = await context.new_page()
                            try:
                                excapper_markets = await exc_scraper.get_match_flow(exc_page, exc_game_id)
                                print(f"    [+] {len(excapper_markets)} mercados extraídos do Excapper.")
                            finally:
                                await exc_page.close()
                        else:
                            print(f"    [!] Não foi possível extrair game_id de: {excapper_url}")
                    elif excapper_url:
                        print(f"    [?] Drop {max_drop:.1f}% < {EXCAPPER_TRIGGER_DROP}% (Excapper opcional). Análise só com drops.")
                    else:
                        print(f"    [?] Sem link Excapper. Análise apenas com dados de drops.")

                    # ── FASE 4: Montar snapshot e enviar para IA ─────────────
                    snapshot = _build_ai_snapshot(match, page_data, excapper_markets, teams)

                    # Calcular hash do alerta para evitar duplicatas
                    alert_hash = hashlib.md5(
                        f"{teams}_{snapshot['live_score']}_{drops[0].get('table', '')}_{drops[0].get('drop_pct', 0):.0f}".encode()
                    ).hexdigest()

                    if alert_hash in sent_alerts:
                        print(f"    [.] Alerta já enviado para {teams}. Pulando.")
                        continue

                    # ── FASE 5: Análise IA ────────────────────────────────────
                    ai_data = {
                        "verdict":          "SUSPICIOUS",
                        "betting_tip":      "Analisar manualmente",
                        "reasoning":        "Drops detectados — análise IA indisponível.",
                        "suggested_odd":    "Live",
                        "risk":             "Médio",
                        "confidence":       5,
                        "stake_suggestion": "Mínimo",
                        "alert_headline":   f"Drop {drops[0].get('drop_pct', 0):.1f}% em {teams}",
                    }

                    print(f"    [*] Enviando para análise IA ({AI_PROVIDER.upper()})...")
                    try:
                        # Injeta contexto do DroppingOdds no prompt (via snapshot enrichido)
                        snapshot["dropping_context_text"] = do_scraper.format_drops_for_ai(match, page_data)

                        ai_raw = await analyzer.analyze_cross_market(snapshot)
                        start  = ai_raw.find("{")
                        end    = ai_raw.rfind("}") + 1
                        if start != -1 and end > 0:
                            ai_data = json.loads(ai_raw[start:end])
                        else:
                            raise ValueError("JSON não encontrado na resposta da IA")
                        print(f"    [✓] IA analisou: Veredito={ai_data.get('verdict')} | Confiança={ai_data.get('confidence')}/10")
                    except Exception as e:
                        print(f"    [!] Erro na análise IA: {e}")

                    # ── FASE 6: Montar e enviar alerta Telegram ──────────────
                    msg = _build_telegram_message(match, page_data, ai_data, snapshot)

                    if send_telegram_alert(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg):
                        print(f"    [OK] Alerta enviado: {teams}!")
                        sent_alerts[alert_hash] = time.time()
                        save_json(SENT_ALERTS_FILE, sent_alerts)
                    else:
                        print(f"    [X] Falha ao enviar alerta para {teams}.")

                print(f"\n[*] Ciclo concluído. Aguardando {CYCLE_SLEEP_SEC}s...")
                await asyncio.sleep(CYCLE_SLEEP_SEC)

            except Exception as e:
                print(f"[!] Erro no ciclo global: {e}")
                await asyncio.sleep(15)


if __name__ == "__main__":
    asyncio.run(main())
