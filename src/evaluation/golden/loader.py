"""Composição dos insumos TRACTIAN com as anotações adicionadas pelo projeto."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote_plus, urlsplit

from pydantic import ValidationError

from src.core.contracts.golden import CaseInput, ExpectedStep, GoldenCase
from src.core.errors import ContractError

__all__ = ["GoldenDataset", "load_golden_dataset"]

_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CASES = _ROOT / "inteli-tractian-project" / "agent-input" / "cases.json"
_DEFAULT_PATHS = _ROOT / "inteli-tractian-project" / "eval" / "expected-paths.json"
_DEFAULT_ANNOTATIONS = Path(__file__).with_name("annotations.json")
_DEFAULT_ADVERSARIAL = Path(__file__).with_name("adversarial_cases.json")


@dataclass(frozen=True)
class GoldenDataset:
    version: str
    fingerprint: str
    cases: tuple[GoldenCase, ...]

    def by_id(self) -> dict[str, GoldenCase]:
        return {case.case_id: case for case in self.cases}

    def base_cases(self) -> tuple[GoldenCase, ...]:
        return tuple(case for case in self.cases if case.case_type == "normal")

    def adversarial_cases(self) -> tuple[GoldenCase, ...]:
        return tuple(case for case in self.cases if case.case_type == "adversarial")


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"golden inválido em {path}: {exc}") from exc


def _fingerprint(parts: list[Any]) -> str:
    canonical = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _route_step(raw: str) -> ExpectedStep:
    match = re.fullmatch(r"(GET|POST|PATCH)\s+(.+)", raw.strip())
    if match is None:
        raise ContractError(f"passo esperado sem método/rota reconhecível: {raw}")
    method, target = match.groups()
    split = urlsplit(target)
    path = unquote_plus(split.path)
    parts = path.strip("/").split("/")
    query = {key: values[-1] for key, values in parse_qs(split.query).items()}

    tool: str
    args: dict[str, Any]
    if method == "GET" and len(parts) == 2 and parts[0] == "assets":
        tool, args = "getAsset", {"assetId": parts[1]}
    elif method == "PATCH" and len(parts) == 2 and parts[0] == "assets":
        tool, args = "updateAssetConfig", {"assetId": parts[1]}
    elif method == "GET" and len(parts) == 3 and parts[0] == "assets":
        mapping = {
            "analyses": "listAnalyses",
            "baseline": "getBaseline",
            "rms": "getRmsSeries",
            "spectrum": "getSpectrum",
            "data-quality": "getDataQuality",
        }
        if parts[2] not in mapping:
            raise ContractError(f"rota esperada desconhecida: {raw}")
        tool, args = mapping[parts[2]], {"assetId": parts[1], **query}
    elif parts[0] == "analyses" and len(parts) == 2 and method == "GET":
        tool, args = "getAnalysis", {"analysisId": parts[1]}
    elif parts[0] == "analyses" and len(parts) == 3 and method == "POST":
        mapping = {
            "reprocess": "reprocessAnalysis",
            "request-specialist": "requestSpecialistAnalysis",
        }
        if parts[2] not in mapping:
            raise ContractError(f"rota esperada desconhecida: {raw}")
        tool, args = mapping[parts[2]], {"analysisId": parts[1]}
    elif parts[0] == "models" and len(parts) == 2 and method == "GET":
        tool, args = "getModel", {"modelId": parts[1]}
    elif (
        parts[0] == "models"
        and len(parts) == 3
        and method == "POST"
        and parts[2] == "request-retraining"
    ):
        tool, args = "requestRetraining", {"modelId": parts[1]}
    elif parts[:2] == ["knowledge", "search"] and method == "GET":
        tool, args = "searchKnowledge", query
    elif parts[0] == "knowledge" and len(parts) == 2 and method == "GET":
        tool, args = "getKnowledgeDoc", {"docId": parts[1]}
    elif parts[0] == "cases" and len(parts) == 3 and method == "POST" and parts[2] == "escalate":
        tool, args = "escalateCase", {"caseId": parts[1]}
    else:
        raise ContractError(f"rota esperada desconhecida: {raw}")
    return ExpectedStep(tool=tool, args_contains=args)


def load_golden_dataset(
    *,
    cases_path: str | Path = _DEFAULT_CASES,
    expected_paths_path: str | Path = _DEFAULT_PATHS,
    annotations_path: str | Path = _DEFAULT_ANNOTATIONS,
    adversarial_path: str | Path = _DEFAULT_ADVERSARIAL,
) -> GoldenDataset:
    raw_cases = _read(Path(cases_path))
    raw_paths = _read(Path(expected_paths_path))
    annotations = _read(Path(annotations_path))
    adversarial_document = _read(Path(adversarial_path))
    if not isinstance(raw_cases, list) or not isinstance(raw_paths, list):
        raise ContractError("cases.json e expected-paths.json precisam conter listas")
    raw_adversarial = (
        adversarial_document.get("cases", [])
        if isinstance(adversarial_document, dict)
        else None
    )
    if not isinstance(raw_adversarial, list):
        raise ContractError("adversarial_cases.json precisa conter uma lista em cases")
    annotation_cases = annotations.get("cases", {}) if isinstance(annotations, dict) else {}
    if not isinstance(annotation_cases, dict):
        raise ContractError("annotations.json precisa conter o objeto cases")

    inputs = {
        case_id: item
        for item in raw_cases
        if isinstance(item, dict) and isinstance(case_id := item.get("id"), str)
    }
    paths = {
        case_id: item
        for item in raw_paths
        if isinstance(item, dict) and isinstance(case_id := item.get("id"), str)
    }
    annotation_cases = {
        str(case_id): value for case_id, value in annotation_cases.items()
    }
    ids = set(inputs)
    if ids != set(paths) or ids != set(annotation_cases):
        raise ContractError(
            "fontes do golden divergiram: "
            f"sem_path={sorted(ids - set(paths))}, "
            f"sem_anotação={sorted(ids - set(annotation_cases))}, "
            f"órfãos={sorted((set(paths) | set(annotation_cases)) - ids)}"
        )

    cases: list[GoldenCase] = []
    try:
        for item in raw_cases:
            case_id = item["id"]
            path_spec = paths[case_id]
            annotation = annotation_cases[case_id]
            expected_path = [_route_step(step["step"]) for step in path_spec["expected_path"]]
            probes = [
                step
                for step in expected_path
                if not step.tool.startswith(("update", "request", "reprocess", "escalate"))
            ]
            payload = {
                **CaseInput(
                    case_id=case_id,
                    ticket_id=item["ticket_id"],
                    message=item["message"],
                    company_id=item["company_id"],
                    user_id=item["user_id"],
                    asset_id=item["asset_id"],
                ).model_dump(),
                "root_question": path_spec["root_question"],
                "degradation_mode": path_spec["mode"],
                "degradation_probes": probes,
                "expected_path": expected_path,
                **annotation,
            }
            cases.append(GoldenCase.model_validate(payload))

        base_ids = {case.case_id for case in cases}
        for item in raw_adversarial:
            if not isinstance(item, dict):
                raise TypeError("caso adversarial precisa ser um objeto")
            adversarial = GoldenCase.model_validate(
                {**item, "source": "generated", "case_type": "adversarial"}
            )
            if adversarial.case_id in base_ids:
                raise ContractError(f"caso adversarial colide com caso base: {adversarial.case_id}")
            cases.append(adversarial)
    except (KeyError, TypeError, ValidationError) as exc:
        raise ContractError(f"caso golden malformado: {exc}") from exc

    adversarial_ids = [
        case.adversarial_id for case in cases if case.case_type == "adversarial"
    ]
    expected_adversarial = {"A1", "A2", "A3", "A4", "A5"}
    if len(adversarial_ids) != 5 or set(adversarial_ids) != expected_adversarial:
        raise ContractError(
            "dataset adversarial precisa conter exatamente A1–A5; "
            f"recebido={adversarial_ids}"
        )

    version = str(annotations.get("version", "0"))
    return GoldenDataset(
        version=version,
        fingerprint=_fingerprint([raw_cases, raw_paths, annotations, adversarial_document]),
        cases=tuple(cases),
    )
