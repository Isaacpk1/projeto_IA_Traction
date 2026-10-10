"""Portão de evidência: recusa o encerramento quando a decisão afirma o que não foi observado.

**Uma regra, não uma tabela.** A primeira versão deste módulo enumerava exigências por
decisão (`agir` pede isto, `escalar` pede aquilo). Aquilo foi escrito depois de olhar
quais casos falhavam numa rodada concreta — o que ajusta o portão àqueles traces em vez
de capturar o princípio. Uma regra derivada das falhas observadas decora; não generaliza.
Esta versão parte do princípio e aceita as consequências, sejam quais forem.

**O princípio.** Uma resolução não pode afirmar o que não observou. `escalar` é, por
definição, a afirmação de que a evidência necessária não está disponível — logo exige ter
emitido ao menos uma consulta cujo retorno sustente essa indisponibilidade: modo
degradado, retorno vazio ou erro. Quem escala sem nenhuma observação assim está alegando
uma lacuna que não verificou, que é o over-escalation descrito no CEN-10.

Repare no que a regra **não** faz: não lista tools, não conhece ativo, não sabe qual é o
caso. Ela vale para qualquer chamado, inclusive para tools que ainda não existem.

**O que não está aqui, de propósito.** "Ação de impacto exige permissão verificada" seria
a segunda regra óbvia — mas ela já é do `PreActionGuard`, que valida
`tool.required_permission` para toda tool `tier: impact` lida do overlay. Duplicá-la aqui
criaria duas fontes de verdade para a mesma exigência. O defeito real lá é outro e está
descrito em `pre_action_guard`: a guarda não distingue "permissão negada" de "permissão
não verificada", e o agente repassa a primeira ao cliente quando o caso é a segunda.

**RNF02.** Nenhuma regra aqui lê o gabarito.
"""

from __future__ import annotations

from typing import Literal

from src.core.contracts.resolution import Resolution
from src.core.contracts.trace import ExecutionTrace

__all__ = ["EvidenceGate", "Variante"]

#: As duas condições ficam **declaradas antes** da rodada que as compara, e nenhuma delas
#: pode ser ajustada depois de ver o resultado. É essa ordem — registrar, depois medir —
#: que separa refinar um princípio de decorar as falhas de uma amostra.
#:
#: - `global`: basta ter observado alguma indisponibilidade na execução.
#: - `por_ativo`: a indisponibilidade precisa ser sobre o ativo do chamado. Mais fiel ao
#:   princípio (ver `partial` num recurso qualquer não sustenta "falta evidência para
#:   *esta* pergunta"), e mais exigente. Qual das duas descreve melhor o comportamento
#:   correto é pergunta empírica, não de gosto.
Variante = Literal["global", "por_ativo"]

#: Retornos que sustentam uma alegação de indisponibilidade. `complete` não sustenta:
#: dado íntegro é evidência de que dá para concluir, não de que falta evidência.
_MODOS_DEGRADADOS = frozenset({"partial", "inconclusive", "conflict", "unavailable"})


class EvidenceGate:
    """Recusa `submit_resolution` quando a decisão afirma uma lacuna não observada.

    Desiste depois de `max_recusas`: um portão que insiste até o teto de passos devolve
    execução sem resolução nenhuma — pior para quem abriu o chamado do que uma resposta
    rasa. Ele redirige a investigação; não ganha queda de braço.
    """

    def __init__(self, *, variante: Variante = "global", max_recusas: int = 2) -> None:
        self.variante = variante
        self.max_recusas = max_recusas
        self.recusas = 0

    def _sobre_o_ativo(self, args: dict | None, asset_id: str | None) -> bool:
        """Na variante `por_ativo`, só conta observação que fala do ativo do chamado."""
        if self.variante == "global" or asset_id is None:
            return True
        if not args:
            return False
        return asset_id in {str(valor) for valor in args.values()}

    def _observou_indisponibilidade(
        self, trace: ExecutionTrace, asset_id: str | None = None
    ) -> bool:
        """Houve alguma consulta cujo retorno sustenta a alegação de lacuna?

        Erro de tool conta: tentar e não conseguir **é** observar indisponibilidade. O que
        não conta é não ter tentado.
        """
        for step in trace.steps:
            if not step.tool or step.tool == "submit_resolution":
                continue
            if not self._sobre_o_ativo(step.args, asset_id):
                continue
            if step.error is not None:
                return True
            if step.mode in _MODOS_DEGRADADOS:
                return True
            if step.result is not None and not step.result.get("data"):
                return True
        return False

    def recusa(
        self, resolution: Resolution, trace: ExecutionTrace, *, asset_id: str | None = None
    ) -> str | None:
        """Mensagem de recusa, ou `None` quando o encerramento pode ser aceito."""
        if self.recusas >= self.max_recusas:
            return None
        if resolution.decision != "escalar":
            return None
        if self._observou_indisponibilidade(trace, asset_id):
            return None
        self.recusas += 1
        return (
            "encerramento recusado: `escalar` afirma que a evidência necessária não está "
            "disponível, mas nenhuma consulta desta execução voltou degradada, vazia ou com "
            "erro. Consulte as fontes que sustentariam essa lacuna — se elas responderem, a "
            "decisão provavelmente não é escalar."
            if self.variante == "global"
            else "encerramento recusado: `escalar` afirma que falta evidência sobre este ativo, "
            "mas nenhuma consulta a ele voltou degradada, vazia ou com erro. Consulte as fontes "
            "do próprio ativo — se elas responderem, a decisão provavelmente não é escalar."
        )
