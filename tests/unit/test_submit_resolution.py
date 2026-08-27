"""Schema e validação da tool terminal."""

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from src.agents.submit_resolution import SUBMIT_RESOLUTION_TOOL, parse_resolution


def test_schema_terminal_e_autocontido_e_fechado():
    schema = SUBMIT_RESOLUTION_TOOL.parameters
    Draft202012Validator.check_schema(schema)
    assert "$defs" not in schema
    assert schema["additionalProperties"] is False


def test_parse_resolution_rejeita_decisao_fora_do_contrato():
    with pytest.raises(ValidationError):
        parse_resolution({"decision": "resolver", "justification": "x"})
