# Módulo de análise de oportunidades KAIROS
# Autor: Desenvolvido para análise de drops de odds em tempo real

import pandas as pd

def process_tables_for_opportunity(tables, match_id, threshold=10.0):
    """
    Processa tabelas aplicando regras de negócio para encontrar oportunidades KAIROS.
    Diferencia tabelas pré-live (para coletar odds iniciais) das ao vivo (para análise de drops).
    
    Args:
        tables (list): Lista de DataFrames
        match_id (str): ID do match para identificação
        threshold (float): Limiar padrão (não usado mais - thresholds específicos por mercado)
        
    Returns:
        dict: {
            'opportunity': DataFrame ou None,
            'prelive_odds': dict com odds iniciais das tabelas pré-live
        }
    
    Thresholds específicos por mercado:
    - 1X2: >= 0.50
    - Total de Gols: >= 0.50
    - Handicap (coluna sharpness): >= 0.30
    - HT Total: >= 0.50
    - HT 1X2: >= 0.40
    """
    
    prelive_odds = {}
    
    for i, table in enumerate(tables):
        if table is None or table.empty:
            continue
            
        print(f"\nAnalisando tabela {i+1}...")
        
        # Identificar se é pré-live ou ao vivo verificando o conteúdo da coluna 'Time'
        is_live = False
        if 'Time' in table.columns:
            # Verificar se há valores numéricos válidos na coluna Time (minutos do jogo)
            time_values = table['Time'].dropna()
            # Se há valores não nulos e pelo menos um é numérico, é ao vivo
            is_live = len(time_values) > 0 and any(pd.to_numeric(val, errors='coerce') >= 0 for val in time_values)
        
        if not is_live:
            print("  📋 Tabela PRÉ-LIVE detectada (coluna 'Time' vazia) - coletando odds iniciais...")
            
            # Coletar odds iniciais das tabelas pré-live
            odds_columns = ['1', 'X', '2', 'Home', 'Draw', 'Away', 'Over', 'Under']
            table_odds = {}
            
            for odds_col in odds_columns:
                if odds_col in table.columns:
                    # Pegar o primeiro valor válido da coluna
                    first_valid_value = None
                    for value in table[odds_col]:
                        if pd.notna(value) and str(value).strip() not in ['', '-']:
                            first_valid_value = str(value).strip()
                            break
                    
                    if first_valid_value:
                        table_odds[odds_col] = first_valid_value
            
            if table_odds:
                prelive_odds[f'tabela_{i+1}'] = table_odds
                print(f"  ✅ Odds iniciais coletadas: {table_odds}")
            else:
                print("  ⚠️  Nenhuma odd inicial encontrada nesta tabela pré-live")
            
            continue
        
        # Tabela ao vivo - verificar se mercado está ativo
        print("  🔴 Tabela AO VIVO detectada - verificando status do mercado...")
        
        market_active = False
        odds_columns = ['1', 'Home', 'Over']
        
        for odds_col in odds_columns:
            if odds_col in table.columns:
                # Verificar se o primeiro valor não nulo não é um traço
                first_valid_value = None
                for value in table[odds_col]:
                    if pd.notna(value) and str(value).strip() != '':
                        first_valid_value = str(value).strip()
                        break
                        
                if first_valid_value and first_valid_value != '-':
                    market_active = True
                    break
                    
        if not market_active:
            print("  ❌ Mercado suspenso ignorado (odds não disponíveis)")
            continue
            
        print("  ✅ Mercado ao vivo e ativo - analisando drops...")
        
        # Buscar por drops significativos apenas em tabelas ao vivo
        drop_column = None
        for col_name in table.columns:
            if 'drop' in col_name.lower():
                drop_column = col_name
                break
                
        if not drop_column:
            print(f"  ⚠️  Coluna 'Drop' não encontrada nesta tabela ao vivo")
            continue
            
        print(f"  🔍 Analisando coluna: {drop_column}")
        
        # Analisar valores da coluna Drop
        for value in table[drop_column]:
            if pd.isna(value) or value == '' or value == '-':
                continue
                
            try:
                # Limpar o valor: remover % e converter para float
                clean_value = str(value).replace('%', '').replace(',', '.').strip()
                numeric_value = float(clean_value)
                
                # Determinar tipo de mercado e threshold específico ANTES da verificação
                market_type = "Desconhecido"
                market_threshold = 0.50  # Padrão
                
                if 'Home' in table.columns and 'Away' in table.columns:
                    # Verificar se é HT (Half Time) ou FT (Full Time)
                    if any('ht' in col.lower() for col in table.columns):
                        market_type = "HT 1X2 (Primeiro Tempo)"
                        market_threshold = 0.40
                    else:
                        market_type = "1X2 (Casa/Empate/Visitante)"
                        market_threshold = 0.50
                elif 'Over' in table.columns and 'Under' in table.columns:
                    # Verificar se é HT Total ou FT Total
                    if any('ht' in col.lower() for col in table.columns):
                        market_type = "HT Total (Primeiro Tempo)"
                        market_threshold = 0.50
                    else:
                        market_type = "Total de Gols (Over/Under)"
                        market_threshold = 0.50
                elif 'Handicap' in table.columns or 'sharpness' in drop_column.lower():
                    market_type = "Handicap Asiático"
                    market_threshold = 0.30
                
                # Verificar se atende ao threshold específico do mercado (valor absoluto)
                if abs(numeric_value) >= market_threshold:
                    print(f"\n🚨 !!! OPORTUNIDADE KAIROS ENCONTRADA !!! no Jogo ID: {match_id} 🚨")
                    print(f"   Drop detectado: {value} (|{numeric_value}| >= {market_threshold})")
                    print(f"   Mercado: {market_type}")
                    print(f"   Tabela: {drop_column} com {len(table)} linhas")
                    
                    # Informações detalhadas do drop
                    drop_info = {
                        'drop_value': value,
                        'numeric_value': numeric_value,
                        'drop_column': drop_column,
                        'market_type': market_type,
                        'table_rows': len(table),
                        'threshold': market_threshold,
                        'detection_time': pd.Timestamp.now().strftime('%H:%M:%S')
                    }
                    
                    return {
                        'opportunity': table,
                        'prelive_odds': prelive_odds,
                        'drop_info': drop_info
                    }
                    
            except (ValueError, TypeError):
                # Ignorar valores que não podem ser convertidos
                continue
                
        print(f"  ✅ Tabela ao vivo analisada - nenhum drop significativo encontrado (thresholds específicos por mercado)")
    
    return {
        'opportunity': None,
        'prelive_odds': prelive_odds
    }