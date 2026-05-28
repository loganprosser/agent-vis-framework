from __future__ import annotations

from typing import Any

from app.tools.base import Tool, ToolResult


class TntCliTool(Tool):
    async def run(self, **kwargs: Any) -> ToolResult:
        # TODO: Replace this mock with an IBM tnt-cli invocation once the exact
        # command contract is known. Keep command construction and parsing here.
        variables = kwargs.get("variables", [])
        domains = kwargs.get("domains", {})
        constraints = kwargs.get("constraints", [])
        reduced_set = []
        for index in range(3):
            case = {}
            for i, variable in enumerate(variables):
                variable_name = variable.get("name", f"var_{i}")
                values = domains.get(variable_name) or ["mock"]
                case[variable_name] = values[index % len(values)]
            reduced_set.append(case)

        for case in reduced_set:
            if case.get("payment_method") == "invoice":
                case["shipping_country"] = "US"
        return ToolResult(
            data={
                "reduced_test_set": reduced_set,
                "constraints_applied": constraints,
                "strategy": "mock pairwise reduction",
            },
            logs=["TntCliTool returned a mocked reduced test set."],
        )
