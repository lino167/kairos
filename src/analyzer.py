import google.generativeai as genai
import asyncio
import json
import os
from abc import ABC, abstractmethod

class BaseAIProvider(ABC):
    @abstractmethod
    async def analyze(self, snapshot: dict) -> str:
        pass

    def _prepare_prompt(self, snapshot: dict) -> str:
        timeline_str = ""
        for event in snapshot.get("unified_timeline", [])[:15]: # Top 15 eventos para contexto
            type_str = f"DROP" if event['type'] == "DROP" else "SUSPENSÃO"
            meta = []
            if event.get("penalty"): meta.append("PENALTY")
            if event.get("red_card"): meta.append("RED CARD")
            meta_str = f" [{', '.join(meta)}]" if meta else ""
            
            # Detalhes numéricos do drop
            drop_detail = ""
            if event['type'] == "DROP":
                drop_detail = f" | {event['selection'].upper()}: {event['prev_value']} -> {event['curr_value']}"

            timeline_str += f"  - {event['time']}' | {event['score']} | {event['market']} (Linha: {event.get('line', 'N/A')}){drop_detail} | {type_str}{meta_str}\n"

        # --- NOVO: Contexto SofaScore Pre-Live ---
        pre_str = ""
        pre_data = snapshot.get("sofascore_prelive_data", {})
        if pre_data:
            pre_str = "CONTEXTO HISTÓRICO (SOFASCORE):\n"
            pre_str += f"  • H2H (V-E-D): {pre_data.get('h2h', 'N/A')}\n"
            pre_str += f"  • Forma Home: {pre_data.get('form', {}).get('home', 'N/A')} | Forma Away: {pre_data.get('form', {}).get('away', 'N/A')}\n"
            if pre_data.get("streaks"):
                pre_str += f"  • Tendências: {'; '.join(pre_data['streaks'][:3])}\n"

        # --- NOVO: Contexto Bet365 Live ---
        b365_str = ""
        b365_data = snapshot.get("bet365_data", {})
        if b365_data:
            b365_str = "PRESSÃO AO VIVO (BET365):\n"
            ap = b365_data.get("ataques_perigosos", {"home": "0", "away": "0"})
            rem = b365_data.get("remates_alvo", {"home": "0", "away": "0"})
            esc = b365_data.get("escanteios", {"home": "0", "away": "0"})
            odds = b365_data.get("odds", {"home": "N/A", "draw": "N/A", "away": "N/A"})
            markets = b365_data.get("markets_available", [])
            
            b365_str += f"  • Ataques Perigosos: {ap['home']} vs {ap['away']}\n"
            b365_str += f"  • Chutes ao Gol: {rem['home']} vs {rem['away']}\n"
            b365_str += f"  • Escanteios: {esc['home']} vs {esc['away']}\n"
            b365_str += f"  • ODDS AO VIVO: Casa {odds['home']} | X {odds['draw']} | Fora {odds['away']}\n"
            if markets:
                b365_str += f"  • MERCADOS ABERTOS: {', '.join(markets[:10])}\n"
            b365_str += f"  • LINK DIRETO: {b365_data.get('direct_link', 'Indisponível')}\n"

        return (
            f"Você é o KAIROS, um Punter Profissional de elite.\n"
            f"Sua missão é explicar as anomalias de mercado cruzando o HISTÓRICO com a PRESSÃO ATUAL e as ODDS AO VIVO.\n\n"
            f"JOGO: {snapshot['match_name']}\n"
            f"PLACAR: {snapshot['live_score']}\n"
            f"MOVIMENTAÇÕES RECENTES:\n{timeline_str or 'Sem eventos no momento.'}\n"
            f"{pre_str}\n"
            f"{b365_str or 'DADOS EM CAMPO: Estatísticas em tempo real não disponíveis no momento.'}\n\n"
            f"REGRAS DO JOGO:\n"
            f"1. VALIDAÇÃO HÍBRIDA: Use as estatísticas da Bet365 para ver se o time que 'deveria' ganhar (SofaScore) está realmente pressionando.\n"
            f"2. ANÁLISE DE VALOR: Use as ODDS AO VIVO da Bet365. Se a odd caiu mas ainda está acima do que a pressão (Ataques Perigosos) justifica, é Green.\n"
            f"3. VISÃO DE SHARK: Identifique 'trap houses' ou 'golden shots'.\n"
            f"4. LINK DIRETO: Mencione que o link direto está disponível no alerta.\n\n"
            f"SAÍDA OBRIGATÓRIA EM JSON:\n"
            f"{{\n"
            f"  \"category\": \"#KAIROS_HYBRID\",\n"
            f"  \"confidence\": \"1-10\",\n"
            f"  \"technical_insight\": \"Sua análise cruzada (Contexto + Pressão + Odds).\",\n"
            f"  \"betting_tip\": \"Entrada direta com a odd aproximada\",\n"
            f"  \"danger_level\": \"Baixo/Médio/Alt\"\n"
            f"}}"
        )

class GeminiProvider(BaseAIProvider):
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        # Modelos detectados como disponiveis no ambiente do usuario
        self.model_names = ['models/gemini-flash-latest', 'models/gemini-2.0-flash', 'models/gemini-pro-latest']
        self.current_idx = 0

    async def analyze(self, snapshot: dict) -> str:
        prompt = self._prepare_prompt(snapshot)

        for _ in range(len(self.model_names)):
            model_name = self.model_names[self.current_idx]
            try:
                print(f"    [*] [Gemini] Tentando com {model_name}...")
                model = genai.GenerativeModel(model_name)
                response = await asyncio.to_thread(model.generate_content, prompt)

                if hasattr(response, 'text') and response.text:
                    return response.text.strip()
            except Exception as e:
                print(f"    [!] Gemini {model_name} falhou: {e}")

            self.current_idx = (self.current_idx + 1) % len(self.model_names)

        return json.dumps({"error": "Gemini Providers failed"})

class DeepSeekProvider(BaseAIProvider):
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com"

    async def analyze(self, snapshot: dict) -> str:
        import aiohttp
        prompt = self._prepare_prompt(snapshot)

        print(f"    [*] [DeepSeek] Iniciando análise...")
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "Você é um analista técnico de apostas."},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False
                }
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                async with session.post(f"{self.base_url}/chat/completions", json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data['choices'][0]['message']['content'].strip()
                    else:
                        error_text = await resp.text()
                        print(f"    [!] Erro DeepSeek API: {resp.status} - {error_text}")
        except Exception as e:
            print(f"    [!] Falha na conexão com DeepSeek: {e}")

        return json.dumps({"error": "DeepSeek analysis failed"})

class ClaudeProvider(BaseAIProvider):
    async def analyze(self, snapshot: dict) -> str:
        # Stub para futura implementação
        return json.dumps({"technical_insight": "Claude Provider não configurado (API Key ausente).", "betting_tip": "N/A", "danger_level": "Alto"})

class KairosAnalyzer:
    def __init__(self, api_key, provider_type="gemini"):
        self.providers = {
            "gemini": GeminiProvider(api_key),
            "deepseek": DeepSeekProvider(api_key), # Reutiliza a chave se for informada
            "claude": ClaudeProvider()
        }
        self.provider = self.providers.get(provider_type, self.providers["gemini"])
        print(f"[*] Analisador iniciado com provedor: {provider_type.upper()}")

    def set_deepseek_key(self, key):
        if "deepseek" in self.providers:
            self.providers["deepseek"].api_key = key

    async def analyze_cross_market(self, snapshot):
        return await self.provider.analyze(snapshot)
