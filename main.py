# Módulo principal do sistema KAIROS
# Orquestra a execução do web scraping e análise de oportunidades

import time
import asyncio
from scraper.web_scraper import get_live_match_ids, scrape_all_available_tables
# from scraper.flashscore_scraper import scrape_flashscore_live_games, find_matching_flashscore_games  # TODO: Implementar scraper do Flashscore
from analyzer.opportunity_analyzer import process_tables_for_opportunity
from scraper.match_info_extractor import get_live_matches_with_details

# TODO: Reimplementar quando scrapers externos estiverem disponíveis
# async def find_matching_external_games(dropping_odds_teams: list, external_games: list, source_name: str = "External") -> list:
#     """
#     Encontra jogos das fontes externas que correspondem aos times do Dropping-Odds
#     
#     Args:
#         dropping_odds_teams: Lista com [home_team, away_team] do Dropping-Odds
#         external_games: Lista de todos os jogos das fontes externas
#         source_name: Nome da fonte externa
#         
#     Returns:
#         list: Jogos das fontes externas que correspondem aos times
#     """
#     # Implementação será adicionada quando scrapers externos estiverem disponíveis
#     return []


async def run_kairos_cycle():
    """
    Executa um ciclo completo do sistema Kairos:
    1. Busca partidas ao vivo no Dropping-Odds
    2. Analisa cada partida em busca de oportunidades
    3. Apresenta oportunidades detectadas com detalhes completos
    
    Nota: Sistema configurado para análise exclusiva do Dropping-Odds
    """
    try:
        from datetime import datetime
        print(f"\n🚀 INICIANDO CICLO KAIROS AVANÇADO - {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*80}")
        
        # ETAPA 1: Buscar partidas ao vivo no Dropping-Odds
        print("📡 Buscando partidas ao vivo no Dropping-Odds...")
        live_matches_details = get_live_matches_with_details()
        
        if not live_matches_details:
            print("⚠️ Nenhuma partida ao vivo encontrada no Dropping-Odds")
            return
        
        print(f"✅ Encontradas {len(live_matches_details)} partidas no Dropping-Odds")
        
        # 📊 Fontes externas desabilitadas
        print("\n📊 Fontes externas (Bet365/Flashscore) não serão utilizadas")
        print("   Continuando apenas com análise do Dropping-Odds...")
        
        # ETAPA 3: Analisar cada partida do Dropping-Odds
        opportunities_found = 0
        
        for i, match_detail in enumerate(live_matches_details, 1):
            match_id = match_detail['game_id']
            print(f"\n{'='*80}")
            print(f"ANALISANDO PARTIDA {i}/{len(live_matches_details)}: {match_id}")
            print(f"Liga: {match_detail.get('league', 'N/A')} | País: {match_detail.get('country', 'N/A')}")
            print(f"Partida: {match_detail.get('home_team', 'N/A')} vs {match_detail.get('away_team', 'N/A')}")
            print(f"Placar: {match_detail.get('score', 'N/A')} | Tempo: {match_detail.get('match_time', 'N/A')}")
            print(f"{'='*80}")
            
            try:
                # Fazer scraping completo das tabelas do evento
                all_tables_dict, all_tables_list = scrape_all_available_tables(match_id)
                
                if not all_tables_list:
                    print(f"⚠️ Nenhuma tabela encontrada para a partida {match_id}")
                    continue
                
                # Analisar tabelas em busca de oportunidades
                result = process_tables_for_opportunity(all_tables_list, match_id, threshold=10.0)
                
                if result and result.get('opportunity') is not None:
                    opportunities_found += 1
                    print(f"\n⚡ OPORTUNIDADE KAIROS #{opportunities_found} DETECTADA NA PARTIDA {match_id}!")
                    
                    # Usar informações já extraídas dos times
                    home_team = match_detail.get('home_team')
                    away_team = match_detail.get('away_team')
                    league = match_detail.get('league')
                    country = match_detail.get('country')
                    
                    if home_team and away_team:
                        print(f"\n[KAIROS] 🎯 DETALHES DA OPORTUNIDADE:")
                        print(f"   Liga: {league}")
                        print(f"   País: {country}")
                        print(f"   Partida: {home_team} vs {away_team}")
                        print(f"   Placar atual: {match_detail.get('score', 'N/A')}")
                        print(f"   Tempo: {match_detail.get('match_time', 'N/A')}")
                        
                        # ETAPA 4: Correspondência com fontes externas não será utilizada
                        print(f"\n[KAIROS] ℹ️ Sistema configurado para análise exclusiva do Dropping-Odds")
                        print(f"   Fontes externas (Bet365/Flashscore) não serão utilizadas nesta versão")
                    
                    else:
                        print(f"\n⚠️ [KAIROS] Informações de times não disponíveis para esta partida")
                        print(f"Home: {home_team}, Away: {away_team}")
                
                else:
                    print(f"\n✅ Nenhuma oportunidade detectada na partida {match_id}")
                
                # Pausa entre análises para não sobrecarregar o servidor
                if i < len(live_matches_details):
                    print(f"\n⏳ Aguardando 2 segundos antes da próxima análise...")
                    time.sleep(2)
            
            except Exception as e:
                print(f"\n❌ Erro ao analisar partida {match_id}: {str(e)}")
                continue
        
        print(f"\n{'='*80}")
        print(f"🏁 ANÁLISE COMPLETA - RESUMO:")
        print(f"   📊 Partidas analisadas: {len(live_matches_details)}")
        print(f"   ⚡ Oportunidades encontradas: {opportunities_found}")
        print(f"   🎯 Modo: Análise exclusiva do Dropping-Odds")
        print(f"   📈 Fontes externas: Não utilizadas")
        print(f"{'='*80}")
            
    except Exception as e:
        print(f"\n❌ Erro no ciclo Kairos: {str(e)}")
        import traceback
        traceback.print_exc()

def main():
    """
    Função principal que executa o loop contínuo do sistema KAIROS
    Executa ciclos de análise a cada 5 minutos
    """
    print("🚀 Sistema KAIROS iniciado - Monitoramento contínuo de oportunidades")
    print("⏰ Ciclos de análise a cada 5 minutos")
    print("🔄 Pressione Ctrl+C para parar")
    print("="*80)
    
    cycle_count = 0
    
    try:
        while True:
            cycle_count += 1
            print(f"\n🔄 === CICLO {cycle_count} === {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
            
            # Executar ciclo de análise
            asyncio.run(run_kairos_cycle())
            
            print(f"\n⏳ Ciclo {cycle_count} concluído. Aguardando 5 minutos para o próximo ciclo...")
            print(f"⏰ Próximo ciclo às: {time.strftime('%H:%M:%S', time.localtime(time.time() + 300))}")
            
            # Aguardar 5 minutos (300 segundos) antes do próximo ciclo
            time.sleep(300)
            
    except KeyboardInterrupt:
        print(f"\n\n🛑 Sistema KAIROS interrompido pelo usuário")
        print(f"📊 Total de ciclos executados: {cycle_count}")
        print("👋 Até logo!")
    except Exception as e:
        print(f"\n❌ Erro crítico no sistema KAIROS: {str(e)}")
        print(f"📊 Ciclos executados antes do erro: {cycle_count}")

if __name__ == "__main__":
    main()