"""Parser OpenAPI — contrato real como fixture (doc 14 §6.2).

O DoD da Fase 1 é explícito: **18 tools geradas do contrato real**. O teste que garante
isso é o primeiro daqui, e o segundo é o que explica *por que* 18 é um número que se
pode errar sem perceber.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tools.core.openapi_parser import load_contract, parse_contract

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def test_gera_dezoito_tools_do_contrato_real(contract_path: Path):
    """DoD da Fase 1. Contagem ≠ 18 é o sinal de detecção do risco RS-01."""
    ops = parse_contract(contract_path)
    assert len(ops) == 18, [o.operation_id for o in ops]
    assert len({o.operation_id for o in ops}) == 18, "operationId duplicado"


def test_path_declarado_duas_vezes_nao_perde_operacao(contract_path: Path):
    """`/assets/{assetId}` aparece duas vezes no contrato — uma com `get`, outra com `patch`.

    YAML não proíbe chave duplicada e o `safe_load` resolve pela última: um parser
    ingênuo perderia `getAsset` e produziria 17 tools **sem erro nenhum**. Este é o teste
    que impede a regressão mais silenciosa da camada.
    """
    ops = {o.operation_id: o for o in parse_contract(contract_path)}

    assert "getAsset" in ops, "getAsset foi engolido pela chave duplicada"
    assert "updateAssetConfig" in ops
    assert ops["getAsset"].method == "get"
    assert ops["updateAssetConfig"].method == "patch"
    assert ops["getAsset"].path == ops["updateAssetConfig"].path

    # e a fusão precisa preservar ambos no documento cru
    doc = load_contract(contract_path)
    item = doc["paths"]["/assets/{assetId}"]
    assert {"get", "patch"} <= set(item)


def test_seed_nao_e_exposto_ao_modelo(contract_path: Path):
    """`seed` é parâmetro de determinismo do experimento, injetado pelo executor.

    Expô-lo no schema convidaria o agente a inventar valores — e o seed é a variável que
    define o regime de degradação de cada execução.
    """
    ops = parse_contract(contract_path)
    consultas = [o for o in ops if o.accepts_seed]

    assert consultas, "nenhuma operação aceita seed — o contrato mudou?"
    for op in consultas:
        assert "seed" not in op.parameters["properties"], op.operation_id
        assert "seed" not in op.required


def test_parametro_de_path_e_sempre_obrigatorio(contract_path: Path):
    for op in parse_contract(contract_path):
        for nome in op.path_params:
            assert nome in op.parameters["properties"], f"{op.operation_id}.{nome}"
            assert nome in op.required, f"{op.operation_id}.{nome} deveria ser obrigatório"


def test_corpo_de_acao_expande_allof(contract_path: Path):
    """O corpo das ações é `allOf: [ActionRequest, {...}]` — precisa ser achatado.

    Sem achatar, o modelo receberia um schema com `allOf` que vários provedores de
    function calling não consomem, e a tool ficaria inutilizável.
    """
    ops = {o.operation_id: o for o in parse_contract(contract_path)}
    update = ops["updateAssetConfig"]

    props = update.parameters["properties"]
    assert "justification" in props
    assert "changes" in props
    assert props["justification"]["minLength"] == 20
    assert "justification" in update.required
    assert "allOf" not in update.parameters


def test_ref_aninhado_e_expandido_ate_o_fim(contract_path: Path):
    """Regressão: um teto de profundidade estrutural truncava schemas profundos.

    `changes.config` sai a sete níveis do `requestBody`. Com o contador subindo a cada
    nível de dicionário — e não só a cada `$ref` —, o schema vinha vazio e ninguém
    percebia, porque `{}` é um schema válido.
    """
    ops = {o.operation_id: o for o in parse_contract(contract_path)}
    changes = ops["updateAssetConfig"].parameters["properties"]["changes"]

    criticality = changes["properties"]["criticality"]
    assert criticality["type"] == "string"
    assert criticality["enum"] == ["low", "medium", "high", "critical"]

    config = changes["properties"]["config"]
    assert config["type"] == "object"
    assert "bearing_specs" in config["properties"]
    assert "part_number" in config["properties"]["bearing_specs"]["properties"]


def test_schema_nao_carrega_ref_residual(contract_path: Path):
    """Nenhum `$ref` pode sobreviver: o provedor não resolve referências ao nosso documento."""

    def varrer(node: object, caminho: str) -> None:
        if isinstance(node, dict):
            assert "$ref" not in node, f"$ref residual em {caminho}"
            for k, v in node.items():
                varrer(v, f"{caminho}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                varrer(v, f"{caminho}[{i}]")

    for op in parse_contract(contract_path):
        varrer(op.parameters, op.operation_id)


def test_operacoes_com_security_sao_as_de_contexto_e_acao(contract_path: Path):
    """`security` no contrato marca as operações que exigem `x-user-id`."""
    ops = {o.operation_id: o for o in parse_contract(contract_path)}
    assert ops["getCurrentUser"].security is True
    assert ops["updateAssetConfig"].security is True
    assert ops["getBaseline"].security is False


def test_parser_ignora_operacao_sem_operation_id(tmp_path: Path):
    contrato = tmp_path / "c.yaml"
    contrato.write_text(
        """
openapi: 3.1.0
info: {title: t, version: "1"}
paths:
  /a:
    get:
      operationId: comId
      responses: {'200': {description: ok}}
  /b:
    get:
      responses: {'200': {description: ok}}
""",
        encoding="utf-8",
    )
    ops = parse_contract(contrato)
    assert [o.operation_id for o in ops] == ["comId"]


def test_ref_ciclico_nao_trava(tmp_path: Path):
    """Schema recursivo existe em contratos reais — o teto de expansão é o que salva."""
    contrato = tmp_path / "c.yaml"
    contrato.write_text(
        """
openapi: 3.1.0
info: {title: t, version: "1"}
components:
  schemas:
    Node:
      type: object
      properties:
        child: {$ref: '#/components/schemas/Node'}
paths:
  /a:
    post:
      operationId: cria
      requestBody:
        content:
          application/json:
            schema: {$ref: '#/components/schemas/Node'}
      responses: {'200': {description: ok}}
""",
        encoding="utf-8",
    )
    ops = parse_contract(contrato)
    assert len(ops) == 1
    assert "child" in ops[0].parameters["properties"]
