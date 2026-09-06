from src.interfaces.dashboard import render_dashboard


def test_render_dashboard_embeds_versioned_frontend_and_data() -> None:
    report = {"run_id": "e1_v1", "execucoes": 2, "metricas": [], "hipoteses": []}
    executions = [{"id": "exec-1", "case_id": "case-1"}]

    html = render_dashboard(
        report,
        execucoes=executions,
        commit="abc123",
        prompt_version="1.1.0",
        gerado="2026-09-06T18:00:00",
    )

    assert "<!doctype html>" in html
    assert "ReactDOM.createRoot" in html
    assert 'role: "tabpanel"' in html
    assert "dashboard-theme" in html
    assert "window.__RELATORIO__" in html
    assert '"id": "exec-1"' in html
    assert "<b>execuções</b> <span class=\"mono\">2</span>" in html
    assert "abc123" in html
    assert "__DASHBOARD_" not in html
    assert "__REPORT_JSON__" not in html


def test_render_dashboard_marks_partial_run_and_escapes_script_end() -> None:
    report = {
        "run_id": "e1_v1",
        "execucoes": 1,
        "metricas": [],
        "hipoteses": [],
        "texto": "</script><script>alert(1)</script>",
    }

    html = render_dashboard(report, alvo=2)

    assert "Rodada incompleta." in html
    assert "1 de 2 execuções\nregistradas" in html
    assert "<\\/script><script>alert(1)<\\/script>" in html
