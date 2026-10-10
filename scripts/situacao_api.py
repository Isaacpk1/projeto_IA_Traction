"""Monta `Situacao` consultando a API industrial viva. I/O fica fora de `src/`."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from src.evaluation.golden.policy import Analise, Situacao

BASE = "http://127.0.0.1:8000"
SEED = "complete"
MODELO = "mdl_vib_v3"


def get(rota: str, *, user_id: str | None = None, seed: str | None = SEED) -> dict:
    url = f"{BASE}{rota}"
    if seed:
        url += ("&" if "?" in rota else "?") + f"seed={seed}"
    req = urllib.request.Request(url)
    if user_id:
        req.add_header("x-user-id", user_id)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return {"_erro": exc.code, "_corpo": exc.read().decode()[:200]}


def _dados(env: dict) -> dict:
    d = env.get("data")
    return d if isinstance(d, dict) else {}


def _cobertura(modelo: dict, machine_type: str) -> tuple[bool, bool]:
    for item in _dados(modelo).get("coverage", []) or []:
        if item.get("machine_type") == machine_type:
            return bool(item.get("supported")), bool(item.get("can_learn_baseline"))
    return False, False


def montar(
    *, user_id: str, asset_id: str, intencao: str, analise_alvo_id: str | None = None
) -> Situacao:
    usuario = get("/users/me", user_id=user_id, seed=None)
    ativo = _dados(get(f"/assets/{asset_id}"))
    baseline = _dados(get(f"/assets/{asset_id}/baseline"))
    dq = _dados(get(f"/assets/{asset_id}/data-quality"))
    lista = _dados(get(f"/assets/{asset_id}/analyses"))
    modelo = get(f"/models/{MODELO}")
    espectro = _dados(get(f"/assets/{asset_id}/spectrum"))
    rms = _dados(get(f"/assets/{asset_id}/rms"))
    req = _dados(modelo).get("requirements") or {}

    analises = tuple(
        Analise(
            id=a["id"],
            status=a.get("status", ""),
            tipo=a.get("type", ""),
            detection_mode=a.get("detection_mode", ""),
            baseline_state_at_detection=a.get("baseline_state_at_detection", ""),
            confidence=float(a.get("confidence") or 0.0),
            limitations=tuple(a.get("limitations") or ()),
        )
        for a in (lista.get("analyses") or [])
    )
    amostras = rms.get("samples") or []
    suportado, aprende = _cobertura(modelo, ativo.get("machine_type", ""))
    return Situacao(
        intencao=intencao,
        user_id=user_id,
        permissoes=frozenset(usuario.get("permissions") or []),
        company_id=ativo.get("company_id", ""),
        asset_id=asset_id,
        machine_type=ativo.get("machine_type", ""),
        criticality=ativo.get("criticality", ""),
        sensor_status=ativo.get("sensor_status", ""),
        baseline_state=baseline.get("state", ""),
        baseline_learnable=bool(baseline.get("learnable")),
        baseline_detection_mode=baseline.get("detection_mode", ""),
        invalidation_reason=baseline.get("invalidation_reason"),
        dq_completeness=dq.get("completeness"),
        dq_snr_db=dq.get("snr_db"),
        dq_staleness=bool(dq.get("staleness_flag")),
        req_min_completeness=float(req.get("min_completeness") or 0.8),
        req_min_snr_db=float(req.get("min_snr_db") or 12.0),
        model_id=MODELO,
        model_processing_state=_dados(modelo).get("processing_state", ""),
        cobertura_suportada=suportado,
        cobertura_aprende_baseline=aprende,
        analises=analises,
        bands_missing=tuple(espectro.get("bands_missing") or ()),
        rms_ultimo=float(amostras[-1]["value"]) if amostras else None,
        alarm_threshold=rms.get("alarm_threshold"),
        analise_alvo_id=analise_alvo_id,
    )
