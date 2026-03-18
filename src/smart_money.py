"""
smart_money.py — Módulo de Análise "Smart Money" (v1.0)
Implementa os indicadores de Volume, Desproporção de Mercado,
Picos Temporais e Filtros de Segurança descritos no documento estratégico Kairos.
"""

import re
from typing import Dict, List, Optional, Tuple


# ===========================================================================
# 1. CONTEXTUALIZAÇÃO DE VOLUME POR LIGA
#    Lígas menores têm liquidez muito menor; o que é suspeito muda por contexto.
# ===========================================================================

# Mapeamento de palavras-chave de liga → perfil de liquidez
LEAGUE_PROFILES = {
    # Grandes Ligas / Oceano
    "premier league":     {"tier": "OCEAN",  "spark_threshold": 15000.0, "disp_threshold": 5000.0},
    "la liga":            {"tier": "OCEAN",  "spark_threshold": 12000.0, "disp_threshold": 4000.0},
    "bundesliga":         {"tier": "OCEAN",  "spark_threshold": 10000.0, "disp_threshold": 3000.0},
    "serie a":            {"tier": "OCEAN",  "spark_threshold": 10000.0, "disp_threshold": 3000.0},
    "ligue 1":            {"tier": "OCEAN",  "spark_threshold":  8000.0, "disp_threshold": 2500.0},
    "champions league":   {"tier": "OCEAN",  "spark_threshold": 20000.0, "disp_threshold": 8000.0},
    "europa league":      {"tier": "OCEAN",  "spark_threshold": 10000.0, "disp_threshold": 4000.0},
    "mls":                {"tier": "OCEAN",  "spark_threshold":  5000.0, "disp_threshold": 2000.0},
    "primeira liga":      {"tier": "MID",    "spark_threshold":  3000.0, "disp_threshold": 1000.0},
    "eredivisie":         {"tier": "MID",    "spark_threshold":  3000.0, "disp_threshold": 1000.0},

    # Médias Ligas / Piscina
    "brasileiro":         {"tier": "MID",    "spark_threshold":  2000.0, "disp_threshold":  800.0},
    "brasileirão":        {"tier": "MID",    "spark_threshold":  2000.0, "disp_threshold":  800.0},
    "brasileirao":        {"tier": "MID",    "spark_threshold":  2000.0, "disp_threshold":  800.0},
    "copa brasil":        {"tier": "MID",    "spark_threshold":  1500.0, "disp_threshold":  600.0},
    "league one":         {"tier": "MID",    "spark_threshold":  1500.0, "disp_threshold":  600.0},
    "championship":       {"tier": "MID",    "spark_threshold":  3000.0, "disp_threshold": 1200.0},
    "superliga":          {"tier": "MID",    "spark_threshold":  1500.0, "disp_threshold":  600.0},
    "segunda":            {"tier": "MID",    "spark_threshold":  1200.0, "disp_threshold":  500.0},

    # Ligas Menores / Lagos
    "indonesia":          {"tier": "LAKE",   "spark_threshold":   300.0, "disp_threshold":  150.0},
    "vietnam":            {"tier": "LAKE",   "spark_threshold":   300.0, "disp_threshold":  150.0},
    "myanmar":            {"tier": "LAKE",   "spark_threshold":   200.0, "disp_threshold":  100.0},
    "serie b":            {"tier": "LAKE",   "spark_threshold":   500.0, "disp_threshold":  200.0},
    "serie c":            {"tier": "LAKE",   "spark_threshold":   250.0, "disp_threshold":  100.0},

    # Sub-categorias / Juventude → Limiar muito baixo para "suspeito"
    "sub-20":             {"tier": "YOUTH",  "spark_threshold":   150.0, "disp_threshold":   80.0},
    "sub-21":             {"tier": "YOUTH",  "spark_threshold":   150.0, "disp_threshold":   80.0},
    "sub-23":             {"tier": "YOUTH",  "spark_threshold":   150.0, "disp_threshold":   80.0},
    "feminino":           {"tier": "YOUTH",  "spark_threshold":   200.0, "disp_threshold":   80.0},
    "women":              {"tier": "YOUTH",  "spark_threshold":   200.0, "disp_threshold":   80.0},
    "u20":                {"tier": "YOUTH",  "spark_threshold":   150.0, "disp_threshold":   80.0},
    "u21":                {"tier": "YOUTH",  "spark_threshold":   150.0, "disp_threshold":   80.0},

    # Default / Desconhecido → conservador
    "_default_":          {"tier": "MID",    "spark_threshold":  1000.0, "disp_threshold":  400.0},
}

# Ícone por tier
TIER_ICON = {
    "OCEAN": "🌊",
    "MID":   "🏞️",
    "LAKE":  "💧",
    "YOUTH": "🎓",
}


def get_league_profile(league_name: str) -> Dict:
    """
    Retorna o perfil de liquidez para uma liga.
    Busca por palavras-chave (case-insensitive) no nome da liga.
    """
    if not league_name:
        return LEAGUE_PROFILES["_default_"]
    league_lower = league_name.lower()
    for keyword, profile in LEAGUE_PROFILES.items():
        if keyword == "_default_":
            continue
        if keyword in league_lower:
            return profile
    return LEAGUE_PROFILES["_default_"]


# ===========================================================================
# 2. DETECÇÃO DE DESPROPORÇÃO DE MERCADO
#    Monitora quando a maior parte do dinheiro entra na odd ALTA (não favorito),
#    o que indica entrada específica de "Smart Money".
# ===========================================================================

DISPROPORTION_RATIO_MIN = 0.70    # 70% do volume na odd alta → suspeito
DISPROPORTION_HIGH_ODD_MIN = 2.50 # Classificar como "odd alta" acima disso


def detect_market_disproportion(
    flow_history: List[Dict],
    league_profile: Dict,
) -> Optional[Dict]:
    """
    Analisa as últimas entradas de fluxo de um mercado buscando desproporção.

    Returns:
        dict com detalhes da desproporção, ou None se não encontrar.
    """
    if not flow_history:
        return None

    # Agrupa por selection e soma volume
    selection_totals: Dict[str, float] = {}
    selection_odds: Dict[str, float] = {}

    for entry in flow_history[:10]:  # Analisa as 10 últimas entradas
        sel = entry.get("selection", "").strip()
        vol = float(entry.get("change_eur", 0) or 0)
        if not sel or vol <= 0:
            continue
        selection_totals[sel] = selection_totals.get(sel, 0) + vol

        # Pega a odd mais recente para essa seleção
        try:
            selection_odds[sel] = float(entry.get("odds", 0) or 0)
        except (ValueError, TypeError):
            pass

    if not selection_totals:
        return None

    total_vol = sum(selection_totals.values())
    if total_vol < league_profile["disp_threshold"]:
        return None  # Volume insuficiente para este contexto de liga

    # Identifica as seleções de odd alta vs odd baixa
    high_odd_vol = 0.0
    low_odd_vol = 0.0
    high_odd_selections = []

    for sel, vol in selection_totals.items():
        odd = selection_odds.get(sel, 0)
        if odd >= DISPROPORTION_HIGH_ODD_MIN:
            high_odd_vol += vol
            high_odd_selections.append((sel, odd, vol))
        else:
            low_odd_vol += vol

    if total_vol == 0 or not high_odd_selections:
        return None

    ratio = high_odd_vol / total_vol

    if ratio >= DISPROPORTION_RATIO_MIN:
        # Encontrou desproporção!
        top_sel = sorted(high_odd_selections, key=lambda x: x[2], reverse=True)
        return {
            "label": "MARKET_DISPROPORTION",
            "description": (
                f"⚠️ {ratio * 100:.0f}% do volume ({high_odd_vol:.0f}€) "
                f"na odd ALTA — não é seguidor de favorito!"
            ),
            "ratio": ratio,
            "high_odd_vol": high_odd_vol,
            "low_odd_vol": low_odd_vol,
            "total_vol": total_vol,
            "top_selections": [(s, o, v) for s, o, v in top_sel[:3]],
        }

    return None


# ===========================================================================
# 3. PICOS DE FINAL DE JOGO (Late-Game Volume Spike)
#    Alerta para aumentos bruscos nos últimos 10-15 minutos (mercado Over Goals).
# ===========================================================================

LATE_GAME_THRESHOLD_MIN = 75   # A partir de qual minuto monitorar
LATE_SPIKE_MULTIPLIER = 2.5    # O volume deve ser X vezes a média anterior


def detect_late_game_spike(
    flow_history: List[Dict],
    current_minute: int,
    league_profile: Dict,
) -> Optional[Dict]:
    """
    Detecta pico de volume nos minutos finais comparado com a média histórica.

    Returns:
        dict com descrição do pico, ou None.
    """
    if current_minute < LATE_GAME_THRESHOLD_MIN:
        return None
    if not flow_history or len(flow_history) < 3:
        return None

    # Separa entradas recentes (consideramos as 2 últimas como "recentes")
    recent_entries = flow_history[:2]
    older_entries = flow_history[2:8]  # Janela de referência histórica

    if not older_entries:
        return None

    # Volume recente
    recent_vol = sum(float(e.get("change_eur", 0) or 0) for e in recent_entries)
    # Média histórica
    avg_older_vol = sum(float(e.get("change_eur", 0) or 0) for e in older_entries) / len(older_entries)

    if avg_older_vol <= 0:
        # Se não há base comparativa, usa o threshold da liga como referência
        if recent_vol >= league_profile["spark_threshold"] * 1.5:
            return {
                "label": "LATE_GAME_SPIKE",
                "description": (
                    f"⏱️ PICO FINAL DE JOGO! Vol {recent_vol:.0f}€ aos {current_minute}' "
                    f"(sem base comparativa, acima do limiar da liga)"
                ),
                "minute": current_minute,
                "recent_vol": recent_vol,
                "avg_vol": 0,
                "multiplier": None,
            }
        return None

    multiplier = recent_vol / avg_older_vol if avg_older_vol > 0 else 0

    if multiplier >= LATE_SPIKE_MULTIPLIER and recent_vol >= league_profile["disp_threshold"]:
        return {
            "label": "LATE_GAME_SPIKE",
            "description": (
                f"⏱️ PICO FINAL DE JOGO! Vol {recent_vol:.0f}€ aos {current_minute}' "
                f"({multiplier:.1f}x a média — possível gol manipulado)"
            ),
            "minute": current_minute,
            "recent_vol": recent_vol,
            "avg_vol": avg_older_vol,
            "multiplier": multiplier,
        }

    return None


# ===========================================================================
# 4. SINAL DE "DROP" NO INTERVALO (HT Drop — Bet365 + Betfair Cross)
#    Detecta quando ocorre queda abrupta de odd no HT (simula comportamento
#    Bet365 onde odd despenca + grandes apostas na Betfair → alta taxa de acerto).
# ===========================================================================

HT_MINUTE_WINDOW = (44, 52)   # Janela de intervalo (min 44 a 52)
HT_DROP_THRESHOLD_PCT = 8.0   # Queda mínima de 8% na odd para disparar
HT_MIN_VOLUME = 500.0         # Volume mínimo no HT para considerar o sinal


def detect_ht_drop(
    flow_history: List[Dict],
    current_minute: int,
    is_halftime: bool,
    league_profile: Dict,
) -> Optional[Dict]:
    """
    Detecta o padrão "Drop da Bet365 no HT":
    Queda de odd + grande volume na janela do intervalo.

    Returns:
        dict com detalhes, ou None.
    """
    in_ht_window = (
        is_halftime
        or HT_MINUTE_WINDOW[0] <= current_minute <= HT_MINUTE_WINDOW[1]
    )
    if not in_ht_window:
        return None

    ht_entries = [
        e for e in flow_history
        if _is_in_ht_range(e.get("score", ""), e.get("time", ""))
    ] or flow_history[:3]

    if not ht_entries:
        return None

    # Encontra a maior queda de odd e o maior volume no período HT
    max_drop = 0.0
    max_vol = 0.0
    for entry in ht_entries:
        pct_raw = str(entry.get("change_pct", "0")).replace("%", "").replace("-", "").strip()
        try:
            pct = float(pct_raw)
        except ValueError:
            pct = 0.0
        max_drop = max(max_drop, pct)
        max_vol = max(max_vol, float(entry.get("change_eur", 0) or 0))

    threshold_vol = max(HT_MIN_VOLUME, league_profile["disp_threshold"])

    if max_drop >= HT_DROP_THRESHOLD_PCT and max_vol >= threshold_vol:
        return {
            "label": "HT_BETFAIR_DROP",
            "description": (
                f"🔔 DROP HT DETECTADO! Queda {max_drop:.1f}% + Vol {max_vol:.0f}€ no intervalo. "
                f"Cross Bet365↔Betfair: probabilidade muito alta!"
            ),
            "drop_pct": max_drop,
            "volume": max_vol,
            "minute": current_minute,
        }

    return None


def _is_in_ht_range(score: str, time_str: str) -> bool:
    """Heurística: verifica se a entrada parece ter ocorrido no intervalo."""
    # Se o tempo inclui "HT", "45", "46", "47" etc.
    if "HT" in str(time_str).upper():
        return True
    try:
        t = int(re.search(r"\d+", str(time_str)).group())
        return HT_MINUTE_WINDOW[0] <= t <= HT_MINUTE_WINDOW[1]
    except (AttributeError, ValueError):
        return False


# ===========================================================================
# 5. FILTROS DE SEGURANÇA (FALSOS POSITIVOS)
# ===========================================================================

SAFE_ODD_LOWER = 1.10   # Odds abaixo disso → ignorar (fix impraticável)
SAFE_ODD_UPPER = 1.25   # Odds até aqui → suspeitas de fix mas descartadas pelo doc
LAY_FLOOD_MULTIPLIER = 3.0  # Quanto maior que o pico original deve ser o contra-fluxo


def apply_safety_filters(
    flow_history: List[Dict],
    current_odd: float,
    primary_change_eur: float,
    league_profile: Dict,
) -> Tuple[bool, List[str]]:
    """
    Aplica os filtros de segurança para eliminar falsos positivos.

    Returns:
        (should_skip: bool, reasons: List[str])
        Se should_skip=True, o sinal deve ser DESCARTADO.
    """
    reasons = []

    # Filtro 1 — Regra da Odd Baixa (1.10 – 1.25)
    # Odds muito esmagadas raramente são fix; volume alto aqui é natural (linha de banca)
    if SAFE_ODD_LOWER <= current_odd <= SAFE_ODD_UPPER:
        reasons.append(
            f"🚫 ODD_MUITO_BAIXA ({current_odd}) — Volume alto em odds 1.1x raramente "
            f"indica manipulação. Documento estratégico recomenda ignorar."
        )
        return True, reasons

    # Filtro 2 — Cancelamento por Lay Bets Massivos (sinal que 'esfriou')
    # Se logo após o pico aparecer contra-fluxo muito maior, o sinal é inválido
    cancel_label = _detect_lay_cancellation(flow_history, primary_change_eur)
    if cancel_label:
        reasons.append(cancel_label)
        return True, reasons

    return False, reasons


def _detect_lay_cancellation(flow_history: List[Dict], spike_vol: float) -> Optional[str]:
    """
    Verifica se houve contra-fluxo massivo (Lay Bet grande) logo após o pico.
    O fluxo de saída é indicado por change_eur negativo ou pela direção da mudança de odd
    (odd subindo novamente após queda = dinheiro saindo).
    """
    if not flow_history or spike_vol <= 0:
        return None

    # Olha as 3 entradas mais recentes depois do pico (índices 1, 2, 3 pois 0 é o pico)
    counter_vol = 0.0
    for entry in flow_history[1:4]:
        pct_raw = str(entry.get("change_pct", "0")).replace("%", "").strip()
        is_reversal = False
        try:
            pct = float(pct_raw)
            # Se a % é POSITIVA (odd subindo novamente) = dinheiro indo embora (Lay ou saída)
            if pct > 0:
                is_reversal = True
        except ValueError:
            pass

        if is_reversal:
            counter_vol += float(entry.get("change_eur", 0) or 0)

    if counter_vol >= spike_vol * LAY_FLOOD_MULTIPLIER:
        return (
            f"🚫 LAY_CANCELLATION — Contra-fluxo de {counter_vol:.0f}€ detectado "
            f"(>{LAY_FLOOD_MULTIPLIER:.0f}x o pico). Sinal 'esfriado' ou tentativa "
            f"de manipulação de mercado. DESCARTADO."
        )

    return None


# ===========================================================================
# FUNÇÃO PRINCIPAL: Roda todos os checks e retorna resultado consolidado
# ===========================================================================

def run_smart_money_analysis(
    flow_history: List[Dict],
    league_name: str,
    current_minute: int,
    is_halftime: bool,
    current_odd: float,
    primary_change_eur: float,
    market_name: str = "",
) -> Dict:
    """
    Executa a análise completa de Smart Money para um mercado específico.

    Returns:
        {
            "league_profile": dict,
            "signals": list[dict],        # sinais positivos disparados
            "safety_filtered": bool,       # True se deve ser descartado
            "filter_reasons": list[str],   # Por quê foi descartado
            "summary_label": str,          # Rótulo legível do resultado
        }
    """
    profile = get_league_profile(league_name)
    tier_icon = TIER_ICON.get(profile["tier"], "🏟️")

    signals = []
    safety_filtered = False
    filter_reasons = []

    # --- Filtros de Segurança PRIMEIRO ---
    safety_filtered, filter_reasons = apply_safety_filters(
        flow_history, current_odd, primary_change_eur, profile
    )

    if not safety_filtered:
        # --- Desproporção de Mercado ---
        disp = detect_market_disproportion(flow_history, profile)
        if disp:
            signals.append(disp)

        # --- Pico Final de Jogo (apenas mercados Over/Under) ---
        is_over_market = "over" in market_name.lower() or "gol" in market_name.lower()
        if is_over_market and current_minute >= LATE_GAME_THRESHOLD_MIN:
            late = detect_late_game_spike(flow_history, current_minute, profile)
            if late:
                signals.append(late)

        # --- Drop no HT ---
        ht = detect_ht_drop(flow_history, current_minute, is_halftime, profile)
        if ht:
            signals.append(ht)

    # --- Resumo ---
    if safety_filtered:
        summary = f"{tier_icon} [{profile['tier']}] SINAL DESCARTADO (Filtro de Segurança)"
    elif signals:
        labels = ", ".join(s["label"] for s in signals)
        summary = f"{tier_icon} [{profile['tier']}] SMART MONEY CONFIRMADO: {labels}"
    else:
        summary = f"{tier_icon} [{profile['tier']}] Sem sinais Smart Money neste mercado"

    return {
        "league_profile": profile,
        "tier_icon": tier_icon,
        "signals": signals,
        "safety_filtered": safety_filtered,
        "filter_reasons": filter_reasons,
        "summary_label": summary,
    }
