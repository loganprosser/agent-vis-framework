"""TestForgeHTTPBridgeClient — talks to the TestForge HTTP bridge via MCP JSON-RPC over HTTP."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.burr_kit.testforge.backend_schemas import (
    RequestLog,
    ToolFeature,
    ToolStatus,
    ValidationError_,
    ValidationResult,
    ValidationWarning,
)
from app.burr_kit.parameter_space import ParameterModel
from app.burr_kit.testforge.test_case_schemas import (
    CoverageReport,
    TestCase,
    TestGenerationResult,
)


class TestForgeError(Exception):
    """Raised when the TestForge backend returns an error."""


class TestForgeHTTPBridgeClient:
    """Sends MCP JSON-RPC requests to the TestForge HTTP bridge."""

    def __init__(self, base_url: str, timeout: float = 60.0, log_dir: Path | None = None):
        self._base_url = base_url.rstrip("/")
        self._endpoint = f"{self._base_url}/mcp"
        self._timeout = timeout
        self._log_dir = log_dir
        self._session = httpx.Client(timeout=timeout)
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        request_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        start = time.monotonic()
        try:
            resp = self._session.post(self._endpoint, json=payload)
            duration_ms = int((time.monotonic() - start) * 1000)
        except httpx.ConnectError as e:
            raise TestForgeError(
                f"Cannot reach TestForge HTTP bridge at {self._endpoint} — "
                f"is the bridge server running? ({e})"
            ) from e

        resp.raise_for_status()
        result = resp.json()

        self._log(tool_name, arguments, result, duration_ms)

        if "error" in result:
            raise TestForgeError(f"MCP error: {result['error'].get('message', result['error'])}")

        content = result.get("result", {}).get("content", [])
        is_error = result.get("result", {}).get("isError", False)
        text = next((c["text"] for c in content if c.get("type") == "text"), None)
        if text is None:
            raise TestForgeError("No text content in MCP response")
        if is_error:
            raise TestForgeError(f"MCP tool error: {text}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise TestForgeError(f"MCP returned non-JSON response: {text[:200]}")

    # -- interface methods --

    def validate_model(self, model: ParameterModel) -> ValidationResult:
        data = self._call_tool("validate_model", self._model_to_args(model))
        return ValidationResult(
            valid=data.get("valid", False),
            errors=[ValidationError_(message=e) for e in data.get("errors", [])],
            warnings=[ValidationWarning(parameter="", message=w) for w in data.get("warnings", [])],
        )

    def generate_test_suite(self, model: ParameterModel) -> TestGenerationResult:
        args = self._model_to_args(model)
        args["coverageLevel"] = model.coverage_level
        data = self._call_tool("generate_test_suite", args)
        return self._parse_generation_result(data)

    def check_installation(self) -> ToolStatus:
        data = self._call_tool("check_tnt_installation", {})
        tnt = data.get("tnt", {})
        return ToolStatus(
            installed=tnt.get("installed", False),
            name="TNT-CLI",
            features=[ToolFeature(name=f) for f in tnt.get("features", [])],
            message=tnt.get("message", ""),
        )

    # -- serialization helpers --

    @staticmethod
    def _model_to_args(model: ParameterModel) -> dict:
        args: dict = {
            "parameters": [
                {"name": p.name, "values": p.values, **({"description": p.description} if p.description else {})}
                for p in model.parameters
            ],
        }
        if model.constraints:
            args["constraints"] = [
                {"type": c.type, "rule": c.rule, **({"description": c.description} if c.description else {})}
                for c in model.constraints
            ]
        return args

    @staticmethod
    def _parse_generation_result(data: dict) -> TestGenerationResult:
        test_cases = [
            TestCase(id=tc.get("id", i + 1), values=tc["values"])
            for i, tc in enumerate(data.get("testCases", []))
        ]
        cov = data.get("coverage", data.get("summary", {}))
        coverage = CoverageReport(
            total_combinations=cov.get("totalPossibleTests", cov.get("totalCombinations", 0)),
            generated_tests=cov.get("generatedTests", len(test_cases)),
            reduction_percentage=float(cov.get("reductionPercentage", 0)),
            coverage_level=cov.get("coverageLevel", 2),
            parameter_coverage=cov.get("parameterCoverage", {}),
        )
        return TestGenerationResult(
            test_cases=test_cases,
            coverage=coverage,
            execution_time=cov.get("executionTime", 0),
            warning=data.get("warning"),
        )

    # -- logging --

    def _log(self, method: str, request_body: dict, response_body: dict, duration_ms: int) -> None:
        if self._log_dir is None:
            return
        entry = RequestLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            method=method,
            endpoint=self._endpoint,
            request_body=request_body,
            response_body=response_body,
            duration_ms=duration_ms,
            backend="http",
        )
        self._log_dir.mkdir(parents=True, exist_ok=True)
        path = self._log_dir / "testforge_requests.jsonl"
        with path.open("a") as f:
            f.write(entry.model_dump_json() + "\n")


# Backwards-compatible alias
TestForgeHTTPClient = TestForgeHTTPBridgeClient
