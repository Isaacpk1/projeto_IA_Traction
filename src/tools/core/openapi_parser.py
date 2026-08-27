"""Contrato OpenAPI ⇒ definições de tool. **Zero conhecimento de domínio (RNF06).**

Nenhum identificador do domínio industrial aparece aqui. Integrar outra API exige um novo
contrato e um novo overlay — este arquivo não muda. A propriedade é verificada por
varredura automatizada, e a violação falha o build.

⚠️ **Chaves duplicadas no contrato.** O contrato fornecido declara `/assets/{assetId}`
duas vezes — uma com `get`, outra com `patch`. YAML não proíbe chave duplicada, e o
`PyYAML` resolve silenciosamente pela última: um `safe_load` ingênuo perderia `getAsset`
e produziria 17 tools em vez de 18, sem erro nenhum. O loader abaixo **funde** mapeamentos
duplicados em vez de sobrescrevê-los.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

__all__ = ["parse_contract", "load_contract", "ParsedOperation", "MergingLoader"]

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

#: Teto de expansões de `$ref` encadeadas. Schemas recursivos existem em contratos reais
#: (um schema que referencia a si mesmo), e sem teto a expansão não termina.
#:
#: ⚠️ O contador sobe **apenas** ao expandir um `$ref` ou um `allOf` — nunca ao descer um
#: nível de dicionário. Contar profundidade estrutural truncaria silenciosamente schemas
#: profundos porém finitos: no contrato real, `changes.criticality` sai a sete níveis do
#: `requestBody` e viria vazio, sem erro nenhum.
_MAX_REF_DEPTH = 8


class MergingLoader(yaml.SafeLoader):
    """`SafeLoader` que funde mapeamentos duplicados em vez de sobrescrever."""


def _construct_mapping(loader: MergingLoader, node: yaml.MappingNode) -> dict:
    loader.flatten_mapping(node)
    out: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        value = loader.construct_object(value_node, deep=True)
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            merged = dict(out[key])
            merged.update(value)
            out[key] = merged
        else:
            out[key] = value
    return out


MergingLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


class ParsedOperation:
    """Uma operação do contrato, já normalizada e sem `$ref` pendente.

    Deliberadamente uma estrutura de dados, não um modelo Pydantic: é interno ao parser
    e vira `ToolDef` (que é validado) na fábrica.
    """

    __slots__ = (
        "operation_id",
        "method",
        "path",
        "summary",
        "description",
        "parameters",
        "path_params",
        "query_params",
        "body_params",
        "required",
        "accepts_seed",
        "security",
    )

    def __init__(
        self,
        *,
        operation_id: str,
        method: str,
        path: str,
        summary: str,
        description: str,
        parameters: dict[str, Any],
        path_params: list[str],
        query_params: list[str],
        body_params: list[str],
        required: list[str],
        accepts_seed: bool,
        security: bool,
    ) -> None:
        self.operation_id = operation_id
        self.method = method
        self.path = path
        self.summary = summary
        self.description = description
        self.parameters = parameters
        self.path_params = path_params
        self.query_params = query_params
        self.body_params = body_params
        self.required = required
        self.accepts_seed = accepts_seed
        self.security = security

    def __repr__(self) -> str:  # pragma: no cover - conveniência de depuração
        return f"<ParsedOperation {self.operation_id} {self.method.upper()} {self.path}>"


def load_contract(path: str | Path) -> dict:
    """Lê o contrato preservando operações declaradas sob chave de path repetida."""
    return yaml.load(Path(path).read_text(encoding="utf-8"), Loader=MergingLoader)


def _resolve(node: Any, doc: dict, ref_depth: int = 0) -> Any:
    """Expande `$ref` e achata `allOf` recursivamente.

    Provedores de function calling consomem JSON Schema autocontido — um `$ref` para
    outro ponto do documento não sobrevive à fronteira. A expansão acontece aqui, uma vez,
    na inicialização.
    """
    if isinstance(node, list):
        return [_resolve(item, doc, ref_depth) for item in node]
    if not isinstance(node, dict):
        return node

    if "$ref" in node:
        if ref_depth >= _MAX_REF_DEPTH:
            return {}
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            return {}
        alvo: Any = doc
        for parte in ref[2:].split("/"):
            if not isinstance(alvo, dict) or parte not in alvo:
                return {}
            alvo = alvo[parte]
        resolvido = _resolve(alvo, doc, ref_depth + 1)
        # campos irmãos do $ref sobrescrevem o alvo (comportamento do OpenAPI 3.1)
        extras = {k: v for k, v in node.items() if k != "$ref"}
        if extras and isinstance(resolvido, dict):
            return {**resolvido, **_resolve(extras, doc, ref_depth + 1)}
        return resolvido

    if "allOf" in node:
        if ref_depth >= _MAX_REF_DEPTH:
            return {}
        fundido: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        for parte in node["allOf"]:
            sub = _resolve(parte, doc, ref_depth + 1)
            if not isinstance(sub, dict):
                continue
            fundido["properties"].update(sub.get("properties", {}))
            fundido["required"].extend(sub.get("required", []))
            for chave in ("description", "type"):
                if chave in sub and chave not in node:
                    fundido.setdefault(chave, sub[chave])
        for chave, valor in node.items():
            if chave == "allOf":
                continue
            resolvido_extra = _resolve(valor, doc, ref_depth + 1)
            if chave == "properties" and isinstance(resolvido_extra, dict):
                fundido["properties"].update(resolvido_extra)
            elif chave == "required" and isinstance(resolvido_extra, list):
                fundido["required"].extend(resolvido_extra)
            else:
                fundido[chave] = resolvido_extra
        fundido["required"] = sorted(set(fundido["required"]))
        return fundido

    return {k: _resolve(v, doc, ref_depth) for k, v in node.items()}


def _clean_schema(schema: Any) -> dict:
    """Reduz um schema do contrato ao subconjunto aceito por function calling.

    `examples`, `format` e afins não atrapalham em todos os provedores, mas `nullable`,
    `$ref` residual e chaves não-JSON-Schema atrapalham em alguns. Manter o schema mínimo
    é o que faz a mesma definição servir Gemini e clientes compatíveis com OpenAI.
    """
    if not isinstance(schema, dict):
        return {"type": "string"}

    permitidas = {
        "type",
        "description",
        "enum",
        "items",
        "properties",
        "required",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "additionalProperties",
    }
    out: dict[str, Any] = {k: v for k, v in schema.items() if k in permitidas}

    if "type" not in out:
        out["type"] = "object" if "properties" in out else "string"
    if isinstance(out.get("items"), dict):
        out["items"] = _clean_schema(out["items"])
    if isinstance(out.get("properties"), dict):
        out["properties"] = {k: _clean_schema(v) for k, v in out["properties"].items()}
    if isinstance(out.get("additionalProperties"), dict):
        out["additionalProperties"] = _clean_schema(out["additionalProperties"])
    return out


def parse_contract(path: str | Path) -> list[ParsedOperation]:
    """Extrai toda operação com `operationId`, na ordem de declaração do contrato."""
    doc = load_contract(path)
    paths = doc.get("paths") or {}
    operacoes: list[ParsedOperation] = []

    for rota, item in paths.items():
        if not isinstance(item, dict):
            continue
        # parâmetros declarados no nível do path valem para todos os métodos
        comuns = [_resolve(p, doc) for p in item.get("parameters", [])]

        for metodo in HTTP_METHODS:
            op = item.get(metodo)
            if not isinstance(op, dict) or not op.get("operationId"):
                continue
            operacoes.append(_parse_operation(op, doc, rota, metodo, comuns))

    return operacoes


def _parse_operation(
    op: dict, doc: dict, rota: str, metodo: str, comuns: list[dict]
) -> ParsedOperation:
    propriedades: dict[str, Any] = {}
    required: list[str] = []
    path_params: list[str] = []
    query_params: list[str] = []
    body_params: list[str] = []
    accepts_seed = False

    for p in comuns + [_resolve(p, doc) for p in op.get("parameters", [])]:
        if not isinstance(p, dict) or "name" not in p:
            continue
        nome, local = p["name"], p.get("in")
        schema = _clean_schema(p.get("schema", {}))
        if p.get("description"):
            schema.setdefault("description", p["description"])

        if local == "path":
            path_params.append(nome)
            required.append(nome)
        elif local == "query":
            query_params.append(nome)
            if p.get("required"):
                required.append(nome)
            # O parâmetro de determinismo é injetado pelo executor, não escolhido pelo
            # modelo: expô-lo no schema convidaria o agente a inventar valores.
            if nome == "seed":
                accepts_seed = True
                continue
        else:
            continue  # header e cookie são responsabilidade do executor
        propriedades[nome] = schema

    body = _resolve(op.get("requestBody") or {}, doc)
    if isinstance(body, dict):
        conteudo_raw = body.get("content") or {}
        conteudo: dict[str, Any] = conteudo_raw if isinstance(conteudo_raw, dict) else {}
        media_raw: Any = conteudo.get("application/json") or next(iter(conteudo.values()), {})
        media: dict[str, Any] = media_raw if isinstance(media_raw, dict) else {}
        schema = _clean_schema(_resolve(media.get("schema", {}), doc)) if media else {}
        for nome, sub in (schema.get("properties") or {}).items():
            body_params.append(nome)
            propriedades[nome] = sub
        required.extend(schema.get("required", []))

    return ParsedOperation(
        operation_id=op["operationId"],
        method=metodo,
        path=rota,
        summary=op.get("summary", "") or "",
        description=op.get("description", "") or "",
        parameters={
            "type": "object",
            "properties": propriedades,
            "required": sorted(set(required)),
            "additionalProperties": False,
        },
        path_params=path_params,
        query_params=query_params,
        body_params=body_params,
        required=sorted(set(required)),
        accepts_seed=accepts_seed,
        security=bool(op.get("security")),
    )
