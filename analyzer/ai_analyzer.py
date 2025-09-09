import google.generativeai as genai
import os
from dotenv import load_dotenv


def configure_gemini():
    """
    Configura a API do Google Gemini.
    Carrega a chave da API do arquivo .env e configura o cliente.
    """
    # Carrega as variáveis do arquivo .env
    load_dotenv()
    
    # Obtém a chave da API
    api_key = os.getenv("GEMINI_API_KEY")
    
    # Verifica se a chave foi carregada
    if not api_key:
        raise ValueError("GEMINI_API_KEY não encontrada no arquivo .env. Verifique se a chave está configurada corretamente.")
    
    # Configura a API
    genai.configure(api_key=api_key)
    print("✅ API do Google Gemini configurada com sucesso!")


def get_ai_analysis(dropping_odds_tables: list, sofascore_stats: dict, match_details: dict, drop_info: dict = None):
    """
    Gera análise de IA usando Google Gemini para dados de partidas de futebol.
    
    Args:
        dropping_odds_tables (list): Lista com tabelas de dropping odds
        sofascore_stats (dict): Estatísticas ao vivo do Sofascore
        match_details (dict): Detalhes da partida (times, placar, tempo)
    
    Returns:
        str: Análise gerada pela IA
    """
    try:
        # Template do prompt para o analista KAIROS
        prompt_template = """
Você é o KAIROS, um analista especialista em detectar MANIPULAÇÃO DE ODDS e MOVIMENTAÇÕES SUSPEITAS no mercado de apostas esportivas.

**DADOS DA PARTIDA:**
- Jogo: {teams}
- Minuto do Jogo: {time}
- Placar: {score}

**INFORMAÇÕES DO DROP DETECTADO:**
{drop_details}

**DADOS DE DROPPING ODDS:**
{dropping_odds}

**SUA MISSÃO - ANÁLISE EXCLUSIVA DE ODDS:**

1. **DETECÇÃO DE MANIPULAÇÃO:**
   - Este drop representa uma MOVIMENTAÇÃO ESTRANHA do mercado?
   - Há sinais de INFORMAÇÃO PRIVILEGIADA ou JOGO MANIPULADO?
   - O padrão de drops indica GRANDE APOSTA de alguém com informação?
   - As odds estão se movendo de forma ARTIFICIAL ou NATURAL?

2. **ANÁLISE DO COMPORTAMENTO DAS ODDS:**
   - Quantas casas de apostas moveram as odds simultaneamente?
   - O drop foi GRADUAL (natural) ou SÚBITO (suspeito)?
   - Há INCONSISTÊNCIA entre diferentes mercados da mesma partida?
   - As odds do FAVORITO vs AZARÃO estão coerentes?

3. **IDENTIFICAÇÃO DE PADRÕES SUSPEITOS:**
   - Mercados SUSPENSOS e reativados com odds diferentes?
   - Drops DESPROPORCIONAIS ao placar atual?
   - Movimentação em HORÁRIOS ESPECÍFICOS (suspeito)?
   - LINHAS DE GOL alteradas sem justificativa no jogo?

4. **CLASSIFICAÇÃO DA OPORTUNIDADE:**
   - JOGO LIMPO: Movimento natural das odds
   - INFORMAÇÃO PRIVILEGIADA: Alguém sabe algo que não sabemos
   - MANIPULAÇÃO SUSPEITA: Padrões artificiais detectados
   - GRANDE APOSTADOR: Volume alto movendo o mercado

**IMPORTANTE:**
- NÃO analise estatísticas do jogo, APENAS as odds
- Foque em detectar se há algo SUSPEITO ou ANORMAL
- Identifique se vale a pena SEGUIR ou EVITAR este movimento
- Seja DIRETO sobre o nível de suspeita

**FORMATO DE RESPOSTA:**
Sempre termine com:
🚨 **CLASSIFICAÇÃO:** [JOGO LIMPO / INFORMAÇÃO PRIVILEGIADA / MANIPULAÇÃO SUSPEITA / GRANDE APOSTADOR]
🎯 **RECOMENDAÇÃO:** [SEGUIR MOVIMENTO / EVITAR / AGUARDAR]
📊 **NÍVEL DE SUSPEITA:** [1-10]/10 (1=Natural, 10=Altamente Suspeito)
⚠️ **JUSTIFICATIVA:** [Explicação técnica do padrão detectado]
"""
        
        # Formata as informações do drop detectado
        drop_details_formatted = ""
        if drop_info:
            drop_details_formatted = f"""- Valor do Drop: {drop_info.get('drop_value', 'N/A')}
- Tipo de Mercado: {drop_info.get('market_type', 'N/A')}
- Coluna Afetada: {drop_info.get('drop_column', 'N/A')}
- Número de Linhas na Tabela: {drop_info.get('table_rows', 'N/A')}
- Threshold Utilizado: {drop_info.get('threshold', 'N/A')}%
- Horário da Detecção: {drop_info.get('detection_time', 'N/A')}"""
        else:
            drop_details_formatted = "Informações específicas do drop não disponíveis."
        
        # Formata os dados de dropping odds
        dropping_odds_formatted = ""
        if dropping_odds_tables:
            for i, table in enumerate(dropping_odds_tables, 1):
                # Mostrar apenas as primeiras e últimas linhas para economizar tokens
                if len(table) > 10:
                    table_summary = f"Tabela {i} ({len(table)} linhas):\n"
                    table_summary += f"Colunas: {list(table.columns)}\n"
                    table_summary += "Primeiras 3 linhas:\n"
                    table_summary += str(table.head(3)) + "\n"
                    table_summary += "Últimas 3 linhas:\n"
                    table_summary += str(table.tail(3)) + "\n"
                    dropping_odds_formatted += table_summary
                else:
                    dropping_odds_formatted += f"\nTabela {i}:\n{str(table)}\n"
        else:
            dropping_odds_formatted = "Nenhum dado de dropping odds disponível."
        
        # Não utilizamos mais estatísticas, apenas análise de odds
        
        # Preenche o template com os dados (sem estatísticas, apenas odds)
        prompt_final = prompt_template.format(
            teams=match_details.get('teams', 'N/A'),
            time=match_details.get('time', 'N/A'),
            score=match_details.get('score', 'N/A'),
            drop_details=drop_details_formatted,
            dropping_odds=dropping_odds_formatted
        )
        
        # Instancia o modelo Gemini
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Gera o conteúdo
        response = model.generate_content(prompt_final)
        
        return response.text
        
    except Exception as e:
        error_msg = f"Erro ao gerar análise com IA: {str(e)}"
        print(f"❌ {error_msg}")
        return f"Análise indisponível: {error_msg}"


if __name__ == '__main__':
    # Exemplo de uso com dados mock
    print("🤖 Testando o Analisador de IA KAIROS...\n")
    
    try:
        # Configura a API
        configure_gemini()
        
        # Dados de exemplo
        mock_dropping_odds = [
            {
                'Casa de Apostas': ['Bet365', 'Betfair', '1xBet'],
                'Odds Iniciais': [2.10, 2.05, 2.15],
                'Odds Atuais': [1.85, 1.80, 1.90],
                'Variação': ['-11.9%', '-12.2%', '-11.6%']
            }
        ]
        
        mock_sofascore_stats = {
            'Posse de Bola': 'Casa 65% - 35% Visitante',
            'Chutes a Gol': 'Casa 8 - 3 Visitante',
            'Chutes no Alvo': 'Casa 5 - 1 Visitante',
            'Escanteios': 'Casa 6 - 2 Visitante',
            'Faltas': 'Casa 12 - 8 Visitante'
        }
        
        mock_match_details = {
            'teams': 'Flamengo vs Palmeiras',
            'time': '67\'',
            'score': '1-0'
        }
        
        # Gera análise
        print("📊 Gerando análise...\n")
        analysis = get_ai_analysis(
            dropping_odds_tables=mock_dropping_odds,
            sofascore_stats=mock_sofascore_stats,
            match_details=mock_match_details
        )
        
        print("🎯 ANÁLISE DO KAIROS:")
        print("=" * 50)
        print(analysis)
        print("=" * 50)
        
    except Exception as e:
        print(f"❌ Erro no teste: {e}")