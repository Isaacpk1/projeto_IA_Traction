"""Contrato do gerador do front.

A plataforma é montada em runtime pelo React; o que este módulo garante é que o
HTML entregue carrega a fonte versionada, embute os dados, não deixa marcador por
substituir e — o item que não é cosmético — **não permite que conteúdo de dado
feche a tag script**.
"""

from src.interfaces.dashboard import render_dashboard

RELATORIO = {"run_id": "e1_v1", "execucoes": 2, "metricas": [], "hipoteses": []}


def test_embute_fonte_versionada_e_dados() -> None:
    html = render_dashboard(
        RELATORIO,
        execucoes=[{"id": "exec-1", "case_id": "case-1"}],
        commit="abc123",
        prompt_version="1.1.0",
        gerado="2026-09-06T18:00:00",
    )

    assert "<!doctype html>" in html
    assert "ReactDOM.createRoot" in html
    # A casca precisa existir antes do React montar, senão o primeiro quadro é vazio.
    assert 'id="app"' in html and "<noscript>" in html
    # React vem do CDN e precisa carregar antes do script da aplicação.
    assert html.index("react-dom.production") < html.index("window.__RELATORIO__")
    assert '"id": "exec-1"' in html
    assert "abc123" in html


def test_nao_deixa_marcador_por_substituir() -> None:
    """Marcador exposto vira texto na tela e denuncia o gerador."""
    html = render_dashboard(RELATORIO)

    for marcador in ("__DASHBOARD_CSS__", "__DASHBOARD_JS__", "__REPORT_JSON__",
                     "__EXECUTIONS_JSON__", "__RUN_ID__", "__COMMIT__", "__NOTICE__"):
        assert marcador not in html


def test_marca_rodada_incompleta() -> None:
    html = render_dashboard(RELATORIO, alvo=5)

    assert "Rodada incompleta." in html
    assert "2 de 5 execuções" in html


def test_rodada_completa_nao_recebe_aviso() -> None:
    assert "Rodada incompleta." not in render_dashboard(RELATORIO, alvo=2)
    assert "Rodada incompleta." not in render_dashboard(RELATORIO)


def test_conteudo_de_dado_nao_fecha_a_tag_script() -> None:
    """Sem esta escapada, um caso com `</script>` no texto injeta HTML na página."""
    relatorio = {**RELATORIO, "texto": "</script><script>alert(1)</script>"}

    html = render_dashboard(relatorio)

    assert "<\\/script><script>alert(1)<\\/script>" in html
    assert "</script><script>alert(1)" not in html
