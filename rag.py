"""Busca lexical BM25 em Python puro (sem dependências externas).

Escolha de projeto: para um corpus pequeno (~160 trechos do PPC) o BM25 dá ótimos
resultados em português, inicia instantaneamente e cabe com folga nos 512 MB do plano
gratuito, ao contrário de embeddings + banco vetorial. A busca custa O(|consulta| x |trechos|),
o que faz dela um endpoint CPU-bound ideal para o teste de carga (não depende de API externa).
"""
import json
import math
import os
import re
import unicodedata
from collections import Counter

STOPWORDS = set("""
a o as os um uma uns umas de do da dos das em no na nos nas por para com sem sobre
e ou que se como mais menos ao aos à às pelo pela pelos pelas seu sua seus suas
este esta estes estas esse essa esses essas isso isto ser sao foi sera ter tem
qual quais quando onde quem quanto quantos quantas me minha meu nosso nossa
curso ppc disciplina""".split())


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def tokenizar(texto):
    toks = re.findall(r"[a-z0-9]+", normalizar(texto))
    return [t for t in toks if len(t) > 1 and t not in STOPWORDS]


class BM25:
    def __init__(self, documentos, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenizar(d)) for d in documentos]
        self.len = [sum(c.values()) for c in self.docs]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 0.0
        self.df = Counter()
        for c in self.docs:
            self.df.update(c.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - df + 0.5) / (df + 0.5)) for t, df in self.df.items()}

    def pontuar(self, consulta):
        termos = tokenizar(consulta)
        notas = []
        for i, c in enumerate(self.docs):
            s = 0.0
            for t in termos:
                f = c.get(t)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * self.len[i] / (self.avg or 1))
                s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / denom
            notas.append(s)
        return notas


class BaseConhecimento:
    """Carrega chunks.json e expõe buscar(consulta, k)."""

    def __init__(self, caminho=None):
        caminho = caminho or os.path.join(os.path.dirname(__file__), "chunks.json")
        with open(caminho, encoding="utf-8") as f:
            self.chunks = json.load(f)
        # o título entra duas vezes para dar peso ao nome da disciplina/seção
        textos = [f"{c['titulo']} {c['titulo']} {c['texto']}" for c in self.chunks]
        self.bm25 = BM25(textos)

    def buscar(self, consulta, k=4):
        notas = self.bm25.pontuar(consulta)
        ranking = sorted(range(len(notas)), key=lambda i: notas[i], reverse=True)[:k]
        return [
            {
                "id": self.chunks[i]["id"],
                "titulo": self.chunks[i]["titulo"],
                "score": round(notas[i], 3),
                "texto": self.chunks[i]["texto"],
            }
            for i in ranking
            if notas[i] > 0
        ]
