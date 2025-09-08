# Módulo principal do sistema KAIROS
# Orquestra a execução do web scraping e análise de oportunidades

import time
from scraper.web_scraper import get_live_match_ids, scrape_all_available_tables
from analyzer.opportunity_analyzer import process_tables_for_opportunity

def main():
    """
    Função principal para executar o sistema KAIROS
    """
    print("🚀 Iniciando sistema KAIROS - Análise de oportunidades em tempo real")
    print("="*80)
    
    # Obter partidas ao vivo
    live_matches = get_live_match_ids()
    
    if live_matches:
        print(f"Encontradas {len(live_matches)} partidas ao vivo")
        
        # Analisar todas as partidas ao vivo
        for i, match_id in enumerate(live_matches, 1):
            print(f"\n{'='*80}")
            print(f"ANALISANDO PARTIDA {i}/{len(live_matches)}: {match_id}")
            print(f"{'='*80}")
            
            try:
                # Extrair todas as tabelas disponíveis
                all_tables_dict, all_tables_list = scrape_all_available_tables(match_id)
                
                print(f"\n{'='*60}")
                print("RESUMO DAS TABELAS")
                print(f"{'='*60}")
                for table_type, table in all_tables_dict.items():
                    if table is not None:
                        print(f"{table_type}: {table.shape[0]} linhas x {table.shape[1]} colunas")
                
                # Procurar por oportunidades significativas
                print(f"\n{'='*60}")
                print("ANÁLISE DE OPORTUNIDADES KAIROS")
                print(f"{'='*60}")
                
                # Usar a função process_tables_for_opportunity
                result = process_tables_for_opportunity(all_tables_list, match_id, threshold=10.0)
                
                # Exibir odds iniciais coletadas das tabelas pré-live
                if result['prelive_odds']:
                    print("\n📋 === ODDS INICIAIS COLETADAS (PRÉ-LIVE) === 📋")
                    for table_name, odds in result['prelive_odds'].items():
                        print(f"  {table_name}: {odds}")
                
                # Verificar se foi encontrada uma oportunidade
                if result['opportunity'] is not None:
                    print(f"\n🎯 === OPORTUNIDADE ENCONTRADA === 🎯")
                    print(f"📊 Dimensões: {result['opportunity'].shape[0]} linhas x {result['opportunity'].shape[1]} colunas")
                    print(f"📋 Colunas: {list(result['opportunity'].columns)}")
                    print("\n📈 Primeiras linhas da tabela:")
                    print(result['opportunity'].head())
                    print(f"\n⚡ OPORTUNIDADE KAIROS DETECTADA NA PARTIDA {match_id}!")
                else:
                    print("\n❌ Nenhuma oportunidade encontrada nesta partida.")
                
                # Pausa entre análises para evitar sobrecarga
                if i < len(live_matches):
                    print("\n⏳ Aguardando 2 segundos antes da próxima análise...")
                    time.sleep(2)
                    
            except Exception as e:
                print(f"\n❌ Erro ao analisar partida {match_id}: {str(e)}")
                continue
        
        print(f"\n{'='*80}")
        print(f"ANÁLISE COMPLETA - {len(live_matches)} PARTIDAS PROCESSADAS")
        print(f"{'='*80}")
            
    else:
        print("Nenhuma partida ao vivo encontrada")

if __name__ == "__main__":
    main()