"""Prompt 5: los dobles son deterministas; Clock e IdGenerator devuelven secuencias fijas."""

import asyncio
from datetime import timedelta

import pytest

from carmen.application.ports.llm import LlmMessage, LlmRole, RequestId
from carmen.domain.time import Instant
from support.builders import at
from support.fakes import FakeEmbeddingAdapter, FakeLlmAdapter, FrozenClock, SeqIdGenerator
from support.fakes.system import EPOCH

pytestmark = pytest.mark.application


def test_frozen_clock_does_not_move_unless_told() -> None:
    clock = FrozenClock()
    assert [clock.now() for _ in range(3)] == [EPOCH, EPOCH, EPOCH]
    clock.advance(timedelta(seconds=5))
    assert clock.now() == at(5)


def test_ticking_clock_gives_a_fixed_sequence() -> None:
    first = FrozenClock(tick=timedelta(milliseconds=250))
    second = FrozenClock(tick=timedelta(milliseconds=250))
    sequence = [first.now() for _ in range(4)]
    assert sequence == [second.now() for _ in range(4)]
    assert sequence == [at(0), at(0.25), at(0.5), at(0.75)]


def test_clock_never_goes_backwards() -> None:
    with pytest.raises(ValueError, match="retrocede"):
        FrozenClock(tick=timedelta(seconds=-1))
    with pytest.raises(ValueError, match="retrocede"):
        FrozenClock().advance(timedelta(seconds=-1))


def test_id_generator_sequence_is_fixed_and_fits_every_prefix() -> None:
    assert [SeqIdGenerator().new_id() for _ in range(2)] == ["000000000001", "000000000001"]
    ids = SeqIdGenerator(start=41)
    assert [ids.new_id() for _ in range(3)] == ["000000000041", "000000000042", "000000000043"]
    with pytest.raises(ValueError, match="empieza"):
        SeqIdGenerator(start=0)


def test_embeddings_are_stable_and_unit_length() -> None:
    first = asyncio.run(FakeEmbeddingAdapter().embed(["monitores en KO", "margen"]))
    second = asyncio.run(FakeEmbeddingAdapter().embed(["monitores en KO", "margen"]))
    assert first == second
    assert first[0] != first[1]
    assert all(len(v) == 1024 for v in first)
    assert abs(sum(x * x for x in first[0]) - 1.0) < 1e-9


def test_llm_script_replays_identically() -> None:
    async def scenario() -> list[str]:
        llm = FakeLlmAdapter(streams=[("Hay ", "4 ", "monitores")])
        messages = [LlmMessage(LlmRole.USER, "¿cuántos monitores en KO?")]
        return [
            c.text
            async for c in llm.stream_text(messages=messages, request_id=RequestId("req_0001"))
        ]

    assert asyncio.run(scenario()) == asyncio.run(scenario()) == ["Hay ", "4 ", "monitores"]


def test_builders_are_anchored_to_the_clock_epoch() -> None:
    assert at() == FrozenClock().now() == Instant.parse("2026-07-27T09:14:20Z")
