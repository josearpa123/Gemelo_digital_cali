"""Validation of the LLM's JSON actions: valid, invalid and outside the whitelist."""

import pytest

from api.llm.actions import InvalidAction, parse_action


@pytest.mark.parametrize(
    "text, accion",
    [
        (
            '{"accion": "provocar_accidente", "calle": "Roosevelt", "duracion_s": 300}',
            "provocar_accidente",
        ),
        ('{"accion": "provocar_accidente"}', "provocar_accidente"),
        ('{"accion": "cambiar_estrategia", "estrategia": "rl"}', "cambiar_estrategia"),
        ('{"accion": "cambiar_demanda", "nivel": "peak"}', "cambiar_demanda"),
        ('{"accion": "pausar"}', "pausar"),
        ('{"accion": "reanudar"}', "reanudar"),
        ('{"accion": "comparar", "a": "rl", "b": "fixed"}', "comparar"),
    ],
)
def test_valid_actions(text, accion):
    assert parse_action(text).accion == accion


@pytest.mark.parametrize(
    "text, kind",
    [
        ('{"accion": "provocar_accidente", "calle": ', "respuesta_invalida"),  # broken JSON
        ("Claro, haré un accidente", "respuesta_invalida"),
        ('["pausar"]', "respuesta_invalida"),
        ('{"accion": "apagar_semaforos"}', "fuera_de_lista"),
        ('{"accion": "desconocida"}', "fuera_de_lista"),
        ('{"comando": "pausar"}', "fuera_de_lista"),
        ('{"accion": "cambiar_estrategia", "estrategia": "caos"}', "parametros"),
        ('{"accion": "cambiar_demanda", "nivel": "infinito"}', "parametros"),
        ('{"accion": "provocar_accidente", "duracion_s": 5}', "parametros"),
        ('{"accion": "pausar", "rm": "-rf"}', "parametros"),  # extra fields are forbidden
    ],
)
def test_invalid_actions_are_rejected(text, kind):
    with pytest.raises(InvalidAction) as err:
        parse_action(text)
    assert err.value.kind == kind
