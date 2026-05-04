import requests
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

API_KEY = os.environ.get("FOOTBALL_API_KEY", "")
BASE = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": API_KEY}

# Competições disponíveis no plano gratuito
COMPETITIONS = {
    "BSA": "Campeonato Brasileiro Série A",
    "PL":  "Premier League",
    "BL1": "Bundesliga",
    "SA":  "Serie A",
    "PD":  "La Liga",
    "FL1": "Ligue 1",
    "CL":  "Champions League",
}

def calcular_medias(comp_id):
    url = f"{BASE}/competitions/{comp_id}/matches"
    params = {"status": "FINISHED"}
    r = requests.get(url, headers=HEADERS, params=params)
    
    if r.status_code != 200:
        print(f"Erro {r.status_code} para {comp_id}: {r.text[:200]}")
        return {}, 2.55

    jogos = r.json().get("matches", [])
    if not jogos:
        return {}, 2.55

    stats = defaultdict(lambda: {
        "gols_marcados_casa": [], "gols_sofridos_casa": [],
        "gols_marcados_fora": [], "gols_sofridos_fora": [],
        "ultimos5_casa": [], "ultimos5_fora": [],
        "posicao": 0
    })

    total_gols = 0
    total_jogos = 0

    for j in sorted(jogos, key=lambda x: x.get("utcDate", "")):
        gh = j["score"]["fullTime"].get("home")
        ga = j["score"]["fullTime"].get("away")
        if gh is None or ga is None:
            continue

        th = j["homeTeam"]["name"]
        ta = j["awayTeam"]["name"]
        total_gols += gh + ga
        total_jogos += 1

        stats[th]["gols_marcados_casa"].append(gh)
        stats[th]["gols_sofridos_casa"].append(ga)
        stats[ta]["gols_marcados_fora"].append(ga)
        stats[ta]["gols_sofridos_fora"].append(gh)

        # Resultado para últimos 5
        res_h = "V" if gh > ga else ("E" if gh == ga else "D")
        res_a = "V" if ga > gh else ("E" if ga == gh else "D")
        stats[th]["ultimos5_casa"].append(res_h)
        stats[ta]["ultimos5_fora"].append(res_a)

    liga_media = round(total_gols / total_jogos, 2) if total_jogos > 0 else 2.55

    medias = {}
    for time, s in stats.items():
        n_casa = max(len(s["gols_marcados_casa"]), 1)
        n_fora = max(len(s["gols_marcados_fora"]), 1)
        
        # Últimos 5 jogos (casa + fora combinados)
        todos_res = s["ultimos5_casa"] + s["ultimos5_fora"]
        ultimos5 = todos_res[-5:] if todos_res else []

        medias[time] = {
            "mediaGolsMarcadosCasa":  round(sum(s["gols_marcados_casa"]) / n_casa, 2),
            "mediaGolsSofridosCasa":  round(sum(s["gols_sofridos_casa"]) / n_casa, 2),
            "mediaGolsMarcadosFora":  round(sum(s["gols_marcados_fora"]) / n_fora, 2),
            "mediaGolsSofridosFora":  round(sum(s["gols_sofridos_fora"]) / n_fora, 2),
            "jogosEmCasa":    n_casa,
            "jogosForaDeCasa": n_fora,
            "ultimos5": ultimos5,
        }

    return medias, liga_media


def buscar_proximos_jogos(comp_id):
    hoje = datetime.utcnow()
    em_10_dias = hoje + timedelta(days=10)
    url = f"{BASE}/competitions/{comp_id}/matches"
    params = {
        "status": "SCHEDULED",
        "dateFrom": hoje.strftime("%Y-%m-%d"),
        "dateTo": em_10_dias.strftime("%Y-%m-%d"),
    }
    r = requests.get(url, headers=HEADERS, params=params)
    if r.status_code != 200:
        return []
    return r.json().get("matches", [])


def main():
    resultado = {}

    for comp_id, comp_nome in COMPETITIONS.items():
        print(f"Processando {comp_nome}...")
        medias, liga_media = calcular_medias(comp_id)
        proximos = buscar_proximos_jogos(comp_id)

        jogos_formatados = []
        for j in proximos[:10]:  # máximo 10 jogos por competição
            th = j["homeTeam"]["name"]
            ta = j["awayTeam"]["name"]
            if th not in medias or ta not in medias:
                continue
            
            ma = medias[th]
            mb = medias[ta]
            
            data_str = ""
            if j.get("utcDate"):
                dt = datetime.fromisoformat(j["utcDate"].replace("Z", "+00:00"))
                data_str = dt.strftime("%d/%m %H:%M")

            jogos_formatados.append({
                "id": f"{th.lower().replace(' ','-')}-vs-{ta.lower().replace(' ','-')}",
                "timeA": {
                    "nome": th,
                    "mediaGolsMarcadosCasa": ma["mediaGolsMarcadosCasa"],
                    "mediaGolsSofridosCasa":  ma["mediaGolsSofridosCasa"],
                    "ultimos5":              ma["ultimos5"],
                    "posicaoTabela":          ma.get("posicao", 0),
                    "jogosEmCasa":            ma["jogosEmCasa"],
                },
                "timeB": {
                    "nome": ta,
                    "mediaGolsMarcadosFora": mb["mediaGolsMarcadosFora"],
                    "mediaGolsSofridosFora":  mb["mediaGolsSofridosFora"],
                    "ultimos5":              mb["ultimos5"],
                    "posicaoTabela":          mb.get("posicao", 0),
                    "jogosForaDeCasa":        mb["jogosForaDeCasa"],
                },
                "dataJogo": data_str,
                "contexto": "",
            })

        resultado[comp_id] = {
            "competicao": comp_nome,
            "rodada": "Próximos jogos",
            "ligaMediaGols": liga_media,
            "atualizadoEm": datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC"),
            "jogos": jogos_formatados,
        }
        print(f"  → {len(jogos_formatados)} jogos encontrados")

    # Salva o JSON
    os.makedirs("data", exist_ok=True)
    with open("data/stats.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"\n✅ stats.json gerado com {sum(len(v['jogos']) for v in resultado.values())} jogos totais.")


if __name__ == "__main__":
    main()
