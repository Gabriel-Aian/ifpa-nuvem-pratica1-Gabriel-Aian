"""Gera chunks.json a partir do texto do PPC (rodar offline, no seu computador).

Uso:
    pdftotext -layout PPC.pdf ppc_raw.txt      # ou use o .txt já extraído
    python ingest_ppc.py ppc_raw.txt chunks.json

Estratégia de divisão:
  * Apêndice I (ementário): 1 trecho por disciplina (nome, período, carga horária,
    ementa e bibliografia). Cada disciplina já é uma unidade semântica completa.
  * Seções 1 a 20: 1 trecho por seção, quebrado em janelas de ~1.400 caracteres
    com sobreposição quando a seção é longa.
  * Seção 6 (estrutura curricular): 1 trecho por período da matriz.
"""
import json
import re
import sys
import unicodedata

MAX_CHARS = 1400
OVERLAP = 200

RUIDO = [
    re.compile(r"^INSTITUTO FEDERAL DE EDUCAÇÃO, CIÊNCIA E TECNOLOGIA DO\s*PARÁ.*$"),
    re.compile(r"^\s*DEPARTAMENTO DE ENSINO\s*$"),
    re.compile(r"^\s*IFPA CAMPUS ANANINDEUA\s*$"),
    re.compile(r"^\s*\d{1,3}\s*$"),  # número de página isolado
    re.compile(r"^Página \d+ de \d+$"),
]


def limpar(linhas):
    saida = []
    for ln in linhas:
        ln = ln.rstrip()
        if any(p.match(ln) for p in RUIDO):
            continue
        saida.append(ln)
    texto = "\n".join(saida)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def janelas(texto, max_chars=MAX_CHARS, overlap=OVERLAP):
    """Quebra texto longo em janelas por parágrafo/linha, com sobreposição."""
    if len(texto) <= max_chars:
        return [texto]
    partes, atual = [], ""
    for par in re.split(r"\n", texto):
        if len(atual) + len(par) + 1 > max_chars and atual:
            partes.append(atual.strip())
            atual = atual[-overlap:] + "\n" + par
        else:
            atual += ("\n" if atual else "") + par
    if atual.strip():
        partes.append(atual.strip())
    return partes


def main(entrada, saida):
    with open(entrada, encoding="utf-8") as f:
        linhas = f.read().split("\n")

    # localiza o início do apêndice (o 2º "APÊNDICE I", o 1º é o sumário)
    idx_apendice = [i for i, l in enumerate(linhas) if l.startswith("APÊNDICE I: EMENTÁRIO")]
    ini_apendice = idx_apendice[-1]

    # localiza o início do corpo (primeira seção "1. JUSTIFICATIVA" fora do sumário)
    idx_just = [i for i, l in enumerate(linhas) if l.strip() == "1. JUSTIFICATIVA"]
    ini_corpo = idx_just[-1]
    # a APRESENTAÇÃO vem antes da seção 1
    idx_apres = [i for i, l in enumerate(linhas[:ini_corpo]) if l.strip() == "APRESENTAÇÃO"]
    ini_apres = idx_apres[-1] if idx_apres else ini_corpo

    chunks = []

    def add(titulo, secao, texto, **extra):
        texto = texto.strip()
        if len(texto) < 40:
            return
        for k, parte in enumerate(janelas(texto)):
            chunks.append({
                "id": len(chunks),
                "titulo": titulo if k == 0 else f"{titulo} (cont.)",
                "secao": secao,
                "texto": parte,
                **extra,
            })

    # ---------- corpo (seções numeradas) ----------
    corpo = linhas[ini_apres:ini_apendice]
    cab = re.compile(r"^(\d{1,2})\. ([A-ZÀ-Ú][A-ZÀ-Ú ,\-ÇÃÕÉÊÍÓÚÂÔ\(\)/]+)$")
    marcas = [(0, "0", "APRESENTAÇÃO")]
    for i, ln in enumerate(corpo):
        m = cab.match(ln.strip())
        if m and m.group(2).strip() == m.group(2).strip().upper() and i > 3:
            marcas.append((i, m.group(1), m.group(2).strip().title()))
    marcas.append((len(corpo), "", ""))

    for (a, num, nome), (b, _, _) in zip(marcas, marcas[1:]):
        bloco = limpar(corpo[a + 1:b])
        titulo = f"Seção {num} - {nome}" if num != "0" else "Apresentação"
        if num == "6":
            # divide a estrutura curricular por período da matriz
            sub = re.split(r"(?m)^(\d)º Período\s*$", bloco)
            intro = sub[0]
            add(titulo, "estrutura", intro)
            for j in range(1, len(sub) - 1, 2):
                add(f"Matriz curricular - {sub[j]}º Período", "matriz", sub[j + 1],
                    periodo=int(sub[j]))
        else:
            add(titulo, "corpo", bloco)

    # ---------- apêndice: ementário por disciplina ----------
    apend = linhas[ini_apendice:]
    starts = [i for i, l in enumerate(apend) if l.startswith("Disciplina:")]
    for n, i in enumerate(starts):
        fim = starts[n + 1] if n + 1 < len(starts) else len(apend)
        # recua para incluir a linha "Período:" que antecede a disciplina
        ini = i
        for back in range(1, 5):
            if i - back >= 0 and apend[i - back].startswith("Período:"):
                ini = i - back
                break
        # o bloco termina antes do "Período:" da próxima disciplina
        corte = fim
        for back in range(1, 5):
            if fim - back > i and apend[fim - back].startswith("Período:"):
                corte = fim - back
                break
        bloco = limpar(apend[ini:corte])
        nome = apend[i].split(":", 1)[1].strip()
        # o PDF quebra o nome em duas linhas em alguns casos
        prox = apend[i + 1].strip() if i + 1 < len(apend) else ""
        if prox and not prox.startswith("Carga Horária") and prox.isupper():
            nome += " " + prox
        m_ch = re.search(r"Carga Horária:\s*([\d]+)\s*h/r", bloco)
        m_per = re.search(r"Período:\s*(\d)", bloco)
        add(f"Ementa - {nome}", "ementa", bloco,
            disciplina=nome,
            carga_horaria=int(m_ch.group(1)) if m_ch else None,
            periodo=int(m_per.group(1)) if m_per else None)

    # reindexa ids
    for k, c in enumerate(chunks):
        c["id"] = k

    with open(saida, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=1)

    n_disc = len({c["disciplina"] for c in chunks if c["secao"] == "ementa"})
    print(f"{len(chunks)} trechos gerados ({n_disc} disciplinas no ementário) -> {saida}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
