"""Agente ReAct (Reasoning + Acting) sobre o PPC, usando Gemini via REST.

Laço:  Pensamento -> Ação (buscar_ppc) -> Observação -> ... -> Resposta final
O modelo responde SEMPRE em JSON, o que torna o parsing robusto mesmo com modelos baratos:

    {"pensamento": "...", "acao": "buscar_ppc", "entrada": "consulta"}
ou  {"pensamento": "...", "resposta_final": "..."}

Usa `requests` direto (sem SDK) para manter a imagem Docker Alpine pequena.
"""
import json
import os
import re
import time

import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
MAX_PASSOS = 4
TIMEOUT_S = 25

SYSTEM_PROMPT = """Você é o assistente acadêmico do curso de Bacharelado em Ciência da Computação do IFPA Campus Ananindeua.
Responda em português, de forma objetiva, SOMENTE com base em trechos do Projeto Pedagógico do Curso (PPC).

Você funciona no padrão ReAct. A cada turno responda com UM objeto JSON, sem texto fora dele:

1) Para consultar o PPC:
{"pensamento": "por que preciso buscar", "acao": "buscar_ppc", "entrada": "consulta curta com palavras-chave"}

2) Quando já tiver informação suficiente:
{"pensamento": "resumo do raciocínio", "resposta_final": "resposta ao aluno"}

Regras:
- Use buscar_ppc sempre que a pergunta depender de dados do curso (ementas, carga horária, períodos, regras, docentes).
- Se a primeira busca não bastar, refine a consulta (no máximo {max_passos} buscas).
- Para perguntas sobre professores/docentes, busque por "corpo docente" junto com o nome da disciplina (Tabela 4 do PPC).
- Se o PPC não tiver a informação, diga isso claramente em resposta_final. Não invente.
- Cite o nome da disciplina ou a seção do PPC que sustenta a resposta."""


class ErroLLM(Exception):
    pass


def chamar_gemini(contents, system=SYSTEM_PROMPT):
    chave = os.environ.get("GEMINI_API_KEY")
    if not chave:
        raise ErroLLM("GEMINI_API_KEY não configurada")
    modelo = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
    corpo = {
        "systemInstruction": {"parts": [{"text": system.replace("{max_passos}", str(MAX_PASSOS))}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 700,
            "responseMimeType": "application/json",
        },
    }
    try:
        r = requests.post(
            GEMINI_URL.format(modelo=modelo),
            headers={"x-goog-api-key": chave, "Content-Type": "application/json"},
            json=corpo,
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as e:
        raise ErroLLM(f"falha de rede ao chamar o Gemini: {e.__class__.__name__}") from e
    if r.status_code != 200:
        raise ErroLLM(f"Gemini respondeu HTTP {r.status_code}")
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError) as e:
        raise ErroLLM("resposta do Gemini em formato inesperado") from e


def extrair_json(texto):
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?|```$", "", texto, flags=re.M).strip()
    try:
        return json.loads(texto)
    except ValueError:
        m = re.search(r"\{.*\}", texto, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
    return None


def formatar_observacao(achados):
    if not achados:
        return "Nenhum trecho relevante encontrado no PPC para essa consulta."
    blocos = [f"[{a['titulo']}]\n{a['texto']}" for a in achados]
    return "\n\n---\n\n".join(blocos)


def executar_react(pergunta, base, llm=chamar_gemini, max_passos=MAX_PASSOS):
    """Roda o laço ReAct. `llm(contents)` -> str JSON. Retorna dict com resposta e trilha."""
    t0 = time.time()
    contents = [{"role": "user", "parts": [{"text": f"Pergunta do aluno: {pergunta}"}]}]
    trilha, fontes, chamadas = [], [], 0

    for passo in range(1, max_passos + 2):
        if passo == max_passos + 1:
            contents.append({"role": "user", "parts": [{
                "text": "Limite de buscas atingido. Responda agora com resposta_final usando o que já sabe."}]})
        saida = llm(contents)
        chamadas += 1
        dados = extrair_json(saida)
        if not dados:
            # modelo fugiu do formato: trata o texto bruto como resposta
            return _resultado(saida.strip(), trilha, fontes, chamadas, t0)
        contents.append({"role": "model", "parts": [{"text": json.dumps(dados, ensure_ascii=False)}]})

        if "resposta_final" in dados:
            trilha.append({"passo": passo, "pensamento": dados.get("pensamento", ""), "tipo": "resposta"})
            return _resultado(str(dados["resposta_final"]), trilha, fontes, chamadas, t0)

        if dados.get("acao") == "buscar_ppc":
            consulta = str(dados.get("entrada", pergunta))[:200]
            achados = base.buscar(consulta, k=3)
            fontes.extend(a["titulo"] for a in achados if a["titulo"] not in fontes)
            trilha.append({
                "passo": passo,
                "pensamento": dados.get("pensamento", ""),
                "acao": f"buscar_ppc({consulta!r})",
                "observacao": [a["titulo"] for a in achados],
            })
            contents.append({"role": "user", "parts": [{
                "text": "Observação:\n" + formatar_observacao(achados)}]})
            continue

        contents.append({"role": "user", "parts": [{
            "text": 'Formato inválido. Responda com {"acao":"buscar_ppc","entrada":"..."} ou {"resposta_final":"..."}.'}]})

    return _resultado("Não consegui concluir a consulta ao PPC.", trilha, fontes, chamadas, t0)


def _resultado(resposta, trilha, fontes, chamadas, t0):
    return {
        "resposta": resposta,
        "fontes": fontes,
        "passos": trilha,
        "chamadas_llm": chamadas,
        "tempo_ms": int((time.time() - t0) * 1000),
    }
