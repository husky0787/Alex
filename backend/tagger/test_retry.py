#!/usr/bin/env python3
"""Focused tests for Tagger model-output retries."""

import unittest
from unittest.mock import AsyncMock, patch

from agents import ModelBehaviorError
from tenacity import wait_none

import agent


class TaggerRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_invalid_model_output(self):
        classification = object()

        with (
            patch.object(agent, "wait_exponential", return_value=wait_none()),
            patch.object(
                agent,
                "classify_instrument",
                new=AsyncMock(
                    side_effect=[ModelBehaviorError("invalid output"), classification]
                ),
            ) as classify,
        ):
            result = await agent.tag_instruments([{"symbol": "VTI", "name": "VTI"}])

        self.assertEqual(result, [classification])
        self.assertEqual(classify.await_count, 2)

    async def test_raises_when_every_attempt_fails(self):
        with (
            patch.object(agent, "wait_exponential", return_value=wait_none()),
            patch.object(
                agent,
                "classify_instrument",
                new=AsyncMock(side_effect=ModelBehaviorError("invalid output")),
            ) as classify,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "Failed to classify all requested instruments"
            ):
                await agent.tag_instruments([{"symbol": "VTI", "name": "VTI"}])

        self.assertEqual(classify.await_count, 5)


if __name__ == "__main__":
    unittest.main()
