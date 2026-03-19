import asyncio
import json
import os
import time
import hashlib
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from ..core.utils import load_json, save_json, send_telegram_alert
from ..core.analyzer import KairosAnalyzer
from ..scrapers.sokkerpro import SokkerProScraper
from ..scrapers.excapper import ExcapperScraper
from ..core.smart_money import run_smart_money_analysis, TIER_ICON

# Carregar variáveis de ambiente
load_dotenv()

# Configuração
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini")

DATA_DIR = "data"
SENT_ALERTS_FILE = os.path.join(DATA_DIR, "sent_alerts.json")

# Limites Estratégicos (Piscina vs Oceano)
MONEY_SPARK_POOL = 500.0      # Gatilho para ligas menores
MONEY_SPARK_OCEAN = 10000.0   # Gatilho para grandes ligas
ODDS_SHIFT_MIN = 10           # Queda mínima de 10%
OCEAN_LIQUIDITY_MIN = 50000.0 # Acima disso é "Oceano"
MIN_MATCH_VOLUME_EUR = 100.0   # Volume mínimo para analisar o jogo
MONEY_SPARK_THRESHOLD = 500.0  # Compatibilidade com prints antigos

# Níveis de Socorro (SokkerPro)
PRESSURE_EXPLOSIVE = 1.0      # APPM acima disso é pressão forte
PRESSURE_DIVERGENCE = 0.4      # Abaixo disso com volume alto é divergência
LOW_PRESSURE_LIMIT = 0.2       # Pressão quase nula ("Cesto de Lixo")
RESISTANT_ODD_LIMIT = 1.5      # Pressão muito alta mas a odd não baixa

# Tempos de Jogo
LATE_GAME_MIN = 80            # Minutos finais para "Cesto de Lixo"
PRE_GAME_DROP_LIMIT = 20       # Queda de 20% pré-jogo é suspeito

# Limites Institucionais (Oceano v2.3)
INSTITUTIONAL_VOL_BARRIER = 50000.0 # IA só acorda se vol anomalia > 50k em jogos grandes
OCEAN_DROP_MIN = 5.0                # Drop institucional (5-8%)
LARGE_TOTAL_VOL = 200000.0          # Volume total para ser "Grande Jogo"

# Mercado Permitidos (Whitelist)
ALLOWED_MARKETS = {
    "Both teams to Score?",
    "First Half Goals 0.5",
    "First Half Goals 1.5",
    "First Half Goals 2.5",
    "Half Time",
    "Match Odds",
    "Over/Under 1.5 Goals",
    "Over/Under 2.5 Goals",
    "Over/Under 3.5 Goals",
    "Over/Under 4.5 Goals",
    "Over/Under 5.5 Goals",
    "Over/Under 6.5 Goals"
}

async def main():
    required_keys = [TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    # (Validação de chaves omitida para brevidade)

    os.makedirs(DATA_DIR, exist_ok=True)
    sent_alerts = load_json(SENT_ALERTS_FILE)

    analyzer = KairosAnalyzer(GEMINI_API_KEY, provider_type=AI_PROVIDER)
    sp_scraper = SokkerProScraper()
    excapper = ExcapperScraper()

    print(f"[*] Analisador iniciado com provedor: {AI_PROVIDER.upper()}")
    print("\n==================================================")
    print("🚀 KAIROS ULTIMATE: MONITORAMENTO EXCAPPER + SOKKERPRO")
    print(f"[*] Limite Volume: {MIN_MATCH_VOLUME_EUR}€ | Anomalia: {MONEY_SPARK_THRESHOLD}€")
    print("==================================================\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )

        page = await context.new_page()

        while True:
            # Garantir que a página principal ainda está aberta
            if page.is_closed():
                print("[!] Página principal fechada. Recriando...")
                page = await context.new_page()

            try:
                # 1. Obter jogos live do Excapper (Money Flow Source)
                live_matches = await excapper.get_live_matches(page)
                print(f"[*] [CYCLE] Analisando {len(live_matches)} jogos ao vivo...")

                for match in live_matches:
                    gid = match["game_id"]
                    teams = match["teams"]
                    volume_raw = match["total_money"].replace("€", "").replace(",", "").strip()
                    volume = float(volume_raw) if volume_raw.replace(".", "").isdigit() else 0.0

                    if volume < MIN_MATCH_VOLUME_EUR:
                        continue

                    print(f"[{time.strftime('%H:%M:%S')}] Investigando {teams} (Vol: {match['total_money']})...")

                    try:
                        # 2. Extrair histórico de fluxo (TODOS os mercados)
                        all_markets_data = await excapper.get_match_flow(page, gid)
                        if not all_markets_data:
                            print(f"      [?] Nenhum dado de mercado extraído para {gid}.")
                            continue

                        print(f"      [+] {len(all_markets_data)} mercados extraídos. Verificando anomalias...")

                        # 3. Detectar Anomalias Significativas
                        found_anomalies = []
                        for m_name, m_data in all_markets_data.items():
                            # Filtro de Mercado (Whitelist)
                            if m_name not in ALLOWED_MARKETS:
                                continue

                            flow_history = m_data["flow"]
                            recent = flow_history[:2]
                            # 1. Definir Liquidez (Piscina vs Oceano)
                            total_vol = float(match['total_money'].replace('€', '').replace(',', '').strip() or 0)
                            is_ocean = total_vol >= OCEAN_LIQUIDITY_MIN

                            for entry in recent:
                                # Limite dinâmico de volume conforme liquidez
                                vol_threshold = MONEY_SPARK_OCEAN if is_ocean else MONEY_SPARK_POOL
                                volume_spike = entry["change_eur"] >= vol_threshold

                                pct_str = entry["change_pct"].replace("%", "").replace("-", "")
                                odds_shift = False
                                try:
                                    if pct_str and float(pct_str) >= ODDS_SHIFT_MIN:
                                        odds_shift = True
                                except: pass

                                current_anomaly = None
                                if volume_spike or odds_shift:
                                    type_str = "OCÉANO" if is_ocean else "PISCINA"
                                    reason = f"[{type_str}] "
                                    if volume_spike and odds_shift: reason += f"COMBO: {entry['change_eur']}€ + Queda {entry['change_pct']}"
                                    elif volume_spike: reason += f"Fluxo: {entry['change_eur']}€"
                                    else: reason += f"Queda Odds: {entry['change_pct']}"
                                    current_anomaly = reason # Assign the constructed reason to current_anomaly

                                if current_anomaly:
                                    if not any(a["reason"] == f"[{m_name} | {entry['selection']}] {current_anomaly}" for a in found_anomalies):
                                        found_anomalies.append({
                                            "reason": f"[{m_name} | {entry['selection']}] {current_anomaly}",
                                            "market": m_name,
                                            "selection": entry["selection"],
                                            "details": entry,
                                            "short_id": f"{m_name}_{entry['selection']}",
                                            "bf_url": m_data["betfair_url"]
                                        })

                        if not found_anomalies:
                            continue

                        primary_anomaly = found_anomalies[0]
                        last_score = primary_anomaly["details"]["score"]
                        alert_hash = hashlib.md5(f"{gid}_{last_score}_{primary_anomaly['short_id']}".encode()).hexdigest()

                        if alert_hash in sent_alerts:
                            print(f"      [.] Alerta já enviado para {primary_anomaly['short_id']}. Pulando.")
                            continue

                        print(f"      [!] ANOMALIA DETECTADA: {primary_anomaly['reason']}")

                        # 4. Enriquecimento via SokkerPro (Stats & Pressure)
                        sp_data = None
                        pre_stats = None

                        # Extrair apenas o primeiro time para a busca no SokkerPro
                        # Algumas vezes o Excapper usa " vs ", outras vezes " - "
                        if " vs " in teams:
                            home = teams.split(" vs ")[0].strip()
                            away = teams.split(" vs ")[1].strip()
                        elif " - " in teams:
                            home = teams.split(" - ")[0].strip()
                            away = teams.split(" - ")[1].strip()
                        else:
                            home, away = teams.strip(), ""

                        print(f"      [*] Buscando no SokkerPro por: '{home}'")
                        sp_page = await context.new_page()
                        try:
                            sp_res = await sp_scraper.search_match(sp_page, home, away)
                            if sp_res["found"]:
                                sp_data = await sp_scraper.get_live_stats(sp_page)
                                pre_stats = await sp_scraper.get_prelive_stats(sp_page)
                        finally:
                            await sp_page.close()

                        # 5. Lógica de Níveis de Prioridade e Detecção de Manipulação
                        level = 1
                        avg_appm = 0
                        is_late_game = False
                        if sp_data:
                            avg_appm = (sp_data['appm_5m']['home'] + sp_data['appm_5m']['away']) / 2

                        # Detectores de Manipulação (Smart Money)
                        manipulation_labels = []
                        pct_change = float(primary_anomaly['details']['change_pct'].replace("%", "").replace("-", "") or 0)

                        try:
                            current_odd = float(primary_anomaly['details']['odds'])
                        except:
                            current_odd = 0.0

                        market_name_up = primary_anomaly['market'].upper()
                        selection_up = primary_anomaly['selection'].upper()
                        current_min = sp_data.get("minute", 0) if sp_data else 0

                        # --- SMART MONEY (módulo externo — análise real pelos dados da anomalia) ---
                        primary_market_flow = all_markets_data.get(
                            primary_anomaly['market'], {}
                        ).get("flow", [])
                        league_name = match.get("league", "")
                        is_halftime = ("HT" in str(match.get("time_text", "")).upper())

                        sm_result = run_smart_money_analysis(
                            flow_history=primary_market_flow,
                            league_name=league_name,
                            current_minute=current_min,
                            is_halftime=is_halftime,
                            current_odd=current_odd,
                            primary_change_eur=primary_anomaly['details']['change_eur'],
                            market_name=primary_anomaly['market'],
                        )

                        # Se o filtro de segurança descartar → pular este sinal
                        if sm_result["safety_filtered"]:
                            for reason in sm_result["filter_reasons"]:
                                print(f"      [SAFE FILTER] {reason}")
                            print(f"      [.] Sinal descartado pelos filtros de segurança Smart Money.")
                            continue

                        # Incorporar sinais Smart Money aos labels de manipulação
                        for sm_signal in sm_result["signals"]:
                            lbl = sm_signal.get("label", "SMART_MONEY")
                            desc = sm_signal.get("description", "")
                            manipulation_labels.append(f"{lbl}: {desc}")
                            # Sinaliza nível máximo automaticamente
                            level = 3
                            print(f"      [SM] {sm_signal['description']}")

                        # Expõe o contexto de liga (+tier) para uso no alerta
                        league_tier = sm_result["league_profile"]["tier"]
                        league_tier_icon = sm_result["tier_icon"]

                        # 1. Detector "HT Smart Money" & Over 0.5 HT Sneak
                        if "HALF TIME" in market_name_up or "1ST HALF" in market_name_up:
                            if "OVER 0.5" in selection_up and last_score == "0-0" and 35 <= current_min <= 45:
                                manipulation_labels.append("HT_GOAL_SNEAK (Golo no final do 1º tempo?)")
                                level = 3
                            else:
                                manipulation_labels.append("HT_SMART_MONEY (Fluxo no 1º Tempo)")
                                level = 3

                        # 2. Detector "Late Goal Anomaly" (Final de Jogo + Pressão Baixa + Volume Alto)
                        if match['is_live'] and current_min >= 80 and "OVER" in market_name_up:
                            if avg_appm <= LOW_PRESSURE_LIMIT:
                                manipulation_labels.append("LATE_GOAL_ANOMALY (Fluxo tardio sem pressão)")
                                level = 3

                        # 3. Detector "Correct Score Dive" (Placares Atípicos)
                        if "CORRECT SCORE" in market_name_up:
                            atypical_scores = ["3-2", "2-3", "4-1", "1-4", "3-3"]
                            if any(score in selection_up for score in atypical_scores):
                                manipulation_labels.append(f"CORRECT_SCORE_DIVE ({selection_up})")
                                level = 3

                        # 4. Detector "HT/FT Turnaround" (Viradas)
                        if "HT/FT" in market_name_up:
                            if "/" in selection_up:
                                parts = selection_up.split("/")
                                if len(parts) >= 2 and parts[0].strip() != parts[1].strip():
                                    manipulation_labels.append(f"HT_FT_TURNAROUND ({selection_up})")
                                    level = 3

                        # 5. Detector "High Odds Sniper" (Odds Altas > 4.0)
                        if current_odd >= 4.0:
                            if not is_ocean:
                                manipulation_labels.append(f"HIGH_ODDS_SNIPER (Odd: {current_odd})")
                                level = 3
                            else:
                                manipulation_labels.append("FAVORITE_DIVERGENCE (Dinheiro no Underdog?)")
                                level = 3

                        # 6. Detector "Match Odds Focus"
                        if "MATCH ODDS" in market_name_up or "MATCH RESULT" in market_name_up:
                            if not any("HIGH_ODDS" in l for l in manipulation_labels):
                                manipulation_labels.append("MATCH_ODDS_FOCUS (Fluxo no Principal)")
                                if pct_change >= 10: level = 3

                        # 7. Detector "Cesto de Lixo" (Heurística Geral)
                        if match['is_live'] and avg_appm <= LOW_PRESSURE_LIMIT and primary_anomaly['details']['change_eur'] >= MONEY_SPARK_POOL * 4:
                            if not any("LATE_GOAL" in l for l in manipulation_labels):
                                manipulation_labels.append("CESTO_DE_LIXO (Suspeita manipulação final)")
                                level = 3

                        # 8. Detector "Pre-Game Drop" (Liquidez Piscina + Queda > 20% sem jogo iniciado)
                        if primary_anomaly['details']['score'] == "0-0" and not is_ocean:
                            if pct_change >= PRE_GAME_DROP_LIMIT:
                                manipulation_labels.append("PRE_GAME_SMART_MONEY (Info Privilegiada?)")
                                level = 3

                        # 9. Detector "Drop Institucional" (Oceano + Volume Massivo + Drop Cirúrgico)
                        is_institutional = False
                        if is_ocean:
                            vol_anomaly = primary_anomaly['details']['change_eur']
                            if vol_anomaly >= INSTITUTIONAL_VOL_BARRIER and OCEAN_DROP_MIN <= pct_change <= 15:
                                manipulation_labels.append(f"INSTITUTIONAL_SMART_MONEY (Vol: {vol_anomaly}€)")
                                is_institutional = True
                                level = 3

                        # Definição de Nível Padrão se não marcado como manipulação
                        if level < 3:
                            if sp_data:
                                if avg_appm >= PRESSURE_EXPLOSIVE or avg_appm <= PRESSURE_DIVERGENCE:
                                    level = 3
                                else:
                                    level = 2
                            else:
                                # Em jogos grandes, só acorda se for institucional ou volume muito anômalo
                                if is_ocean:
                                    if primary_anomaly['details']['change_eur'] >= INSTITUTIONAL_VOL_BARRIER:
                                        level = 3
                                    else:
                                        level = 2
                                else:
                                    if primary_anomaly['details']['change_eur'] >= MONEY_SPARK_POOL * 2:
                                        level = 3
                                    else:
                                        level = 2

                        # Filtro Final de Custo (Oceano): Só acorda IA se for institucional ou volume absurdamente alto
                        if is_ocean and level == 3 and not is_institutional:
                            if primary_anomaly['details']['change_eur'] < INSTITUTIONAL_VOL_BARRIER:
                                print(f"      [.] Oceano detectado mas volume ({primary_anomaly['details']['change_eur']}€) abaixo do barreira institucional (€50k).")
                                level = 2

                        if level == 1:
                            print(f"      [.] Nível 1 (Ruído). Pulando.")
                            continue

                        print(f"      [!] GAILHO NÍVEL {level} DETECTADO. Manipulação: {manipulation_labels or 'Nenhuma'}")

                        # 6. Análise IA (Nível 3 sempre; enriquece com SokkerPro se disponível)
                        ai_data = {
                            "verdict": "NOISE",
                            "betting_tip": "N/A",
                            "reasoning": "Análise automática indisponível.",
                            "suggested_odd": "N/A",
                            "risk": "Médio",
                            "confidence": 5,
                            "stake_suggestion": "Mínimo",
                            "alert_headline": "Anomalia detectada",
                        }

                        if level == 3:
                            ai_snapshot = {
                                "match_name": teams,
                                "live_score": last_score,
                                "is_live": match["is_live"],
                                "current_minute": current_min,
                                "primary_anomaly": primary_anomaly,
                                "all_anomalies": found_anomalies,
                                "sokkerpro_live": sp_data,       # pode ser None
                                "sokkerpro_pre": pre_stats,       # pode ser None
                                "smart_money_result": sm_result,  # ← NOVO: contexto SM
                                "strategic_context": {
                                    "is_ocean": is_ocean,
                                    "avg_appm": avg_appm,
                                    "is_divergence": avg_appm <= PRESSURE_DIVERGENCE,
                                    "manipulation_labels": manipulation_labels,
                                },
                            }
                            ai_raw = await analyzer.analyze_cross_market(ai_snapshot)
                            try:
                                # Extração robusta de JSON
                                start = ai_raw.find('{')
                                end   = ai_raw.rfind('}') + 1
                                if start != -1 and end > 0:
                                    ai_data = json.loads(ai_raw[start:end])
                                else:
                                    raise ValueError("JSON não encontrado na resposta")
                            except Exception as e:
                                print(f"      [!] Falha ao processar JSON da IA: {e}")
                                cleaned = ai_raw.replace("```json", "").replace("```", "").strip()
                                ai_data = {
                                    "verdict": "SUSPICIOUS",
                                    "betting_tip": "BACK/LAY (Ver Detalhes)",
                                    "reasoning": (cleaned[:480] + "…") if len(cleaned) > 480 else cleaned,
                                    "suggested_odd": "Live",
                                    "risk": "Médio",
                                    "confidence": 6,
                                    "stake_suggestion": "Mínimo",
                                    "alert_headline": "Anomalia detectada — análise manual recomendada",
                                }

                        # ── 7. Formatação do Alerta Telegram ──────────────────────────────
                        league        = match.get("league", "Futebol")
                        excapper_url  = match.get("url", "https://www.excapper.com")
                        time_info     = match["time_text"]

                        # Confiança e estrelas
                        try:
                            conf_val = int(ai_data.get("confidence", 5))
                        except (ValueError, TypeError):
                            conf_val = 5
                        conf_val  = max(1, min(10, conf_val))
                        stars     = "⭐" * (conf_val // 2 if conf_val > 1 else 1)

                        # Contexto Smart Money para o cabeçalho
                        sm_tier_icon  = sm_result["tier_icon"]
                        sm_tier_label = sm_result["league_profile"]["tier"]

                        # Verdict → ícone
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

                        # Headline de impacto (gerada pela IA ou fallback)
                        headline = ai_data.get("alert_headline") or primary_anomaly["reason"]
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

                        # Mercados adicionais (cross-market resumido)
                        cross_lines = ""
                        if len(found_anomalies) > 1:
                            cross_lines = "\n<b>🔀 Cross-Market:</b>\n"
                            for anom in found_anomalies[1:4]:   # máx 3 extras
                                adet = anom.get("details", {})
                                cross_lines += (
                                    f"  • <code>{anom['market']}</code> "
                                    f"[{anom['selection']}] "
                                    f"→ {adet.get('change_eur', 0):.0f}€ / Odd {adet.get('odds', '?')}\n"
                                )

                        # Sinais SM formatados
                        sm_signals_str = ""
                        for sig in sm_result.get("signals", []):
                            sm_signals_str += f"  ├ <code>{sig['label']}</code>: {sig.get('description', '')}\n"

                        # Labels de manipulação (detectores clássicos + SM filtrados)
                        classic_labels = [
                            l for l in manipulation_labels
                            if not any(
                                sm_kw in l
                                for sm_kw in ["MARKET_DISPROPORTION", "LATE_GAME_SPIKE", "HT_BETFAIR_DROP"]
                            )
                        ]

                        # ── Montagem final da mensagem ───────────────────────────────────
                        msg = (
                            f"🛰️ <b>KAIROS INTELLIGENCE</b> — <code>v3.1</code>\n"
                            f"{'━' * 28}\n"
                            f"<b>📣 {headline}</b>\n"
                            f"{'━' * 28}\n\n"
                            f"🏆 <b>Liga:</b> {league}  {sm_tier_icon} <code>[{sm_tier_label}]</code>\n"
                            f"⚽ <b>Partida:</b> {teams}\n"
                        )

                        if match["is_live"]:
                            msg += f"🔴 <b>Live:</b> <code>{last_score}</code>  ⏱ <code>{time_info}</code>\n"
                        else:
                            msg += f"🔵 <b>Horário:</b> <code>{time_info}</code>\n"

                        msg += (
                            f'🔗 <a href="{excapper_url}">Ver no Excapper</a>\n\n'
                            f"{'─' * 28}\n"
                            f"🧠 <b>VEREDITO IA:</b>  {verdict_str}\n"
                            f"📌 <b>Análise:</b> {ai_data.get('reasoning', 'N/A')}\n\n"
                            f"{'─' * 28}\n"
                            f"💰 <b>APOSTA:</b>  <code>{str(ai_data.get('betting_tip', 'N/A')).upper()}</code>\n"
                            f"🎯 <b>Odd Mín.:</b> <code>{ai_data.get('suggested_odd', 'Live')}</code>  "
                            f"📊 <b>Stake:</b> {stake_badge}\n"
                            f"⭐ <b>Confiança:</b> {conf_val}/10  {stars}\n"
                            f"⚠️ <b>Risco:</b> {ai_data.get('risk', 'Médio')}\n"
                        )

                        # Bloco Smart Money (só se houver sinais)
                        if sm_signals_str:
                            msg += (
                                f"\n{'─' * 28}\n"
                                f"🔬 <b>SMART MONEY SIGNALS:</b>\n"
                                f"{sm_signals_str}"
                            )

                        # Bloco cross-market
                        if cross_lines:
                            msg += cross_lines

                        # Labels clássicos de manipulação
                        if classic_labels:
                            msg += (
                                f"\n⚙️ <b>Detectores Ativos:</b>\n"
                                + "".join(f"  • <code>{l}</code>\n" for l in classic_labels[:4])
                            )

                        # Rodapé com link Betfair
                        msg += (
                            f"\n{'━' * 28}\n"
                            f'🔗 <a href="{primary_anomaly["bf_url"]}">⚡ ABRIR NA BETFAIR</a>'
                        )

                        if send_telegram_alert(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg):
                            print(f"      [OK] Alerta enviado com sucesso para {teams}!")
                            sent_alerts[alert_hash] = time.time()
                            save_json(SENT_ALERTS_FILE, sent_alerts)
                        else:
                            print(f"      [X] Falha ao enviar alerta para {teams}. Verifique logs do Telegram acima.")

                    except Exception as e:
                        print(f"      [!] Erro na análise da partida {gid}: {f'{e.__class__.__name__}: {e}'}")

                print(f"[*] Ciclo finalizado. Aguardando 60s...")
                await asyncio.sleep(60)

            except Exception as e:
                print(f"🚀 Erro no ciclo global: {e}")
                await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
