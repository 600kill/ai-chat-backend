"""Initialize tools from LangGraph tools directory into database."""

import importlib
import inspect
import pkgutil
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

# 离线 CLI 入口必须先导入全部 ORM 模型，否则 relationship mapper 配置失败
import app.models

[
    importlib.import_module("app.models." + m.name)
    for m in pkgutil.iter_modules(app.models.__path__)
]

from app.services.database import database_service
from app.services.agent_service import AgentService
from app.core.langgraph.tools.calculator import calculator
from app.core.langgraph.tools.document_search import document_search
from app.core.langgraph.tools.generate_chart import generate_chart
from app.core.langgraph.tools.duckduckgo_search import duckduckgo_search_tool
from app.core.langgraph.tools.ask_human import ask_human


class ToolInitializer:
    """Initialize and register tools from LangGraph to database."""
    
    def __init__(self):
        self.agent_service = AgentService(database_service.get_session_maker())
    
    def get_tool_schema(self, tool: BaseTool) -> Dict[str, Any]:
        """Extract JSON schema from LangChain tool."""
        input_schema = {
            "type": "object",
            "properties": {},
            "required": []
        }

        func = getattr(tool, "func", None)
        if func is not None:
            # @tool 装饰的函数：从函数签名提取
            sig = inspect.signature(func)

            for param_name, param in sig.parameters.items():
                # 运行时注入参数（RunnableConfig/callback）不属于 LLM 输入 schema
                if param.annotation is RunnableConfig or param_name in ("config", "run_manager"):
                    continue

                param_type = param.annotation

                # Determine JSON type
                if param_type == str:
                    json_type = "string"
                elif param_type == int:
                    json_type = "integer"
                elif param_type == float:
                    json_type = "number"
                elif param_type == bool:
                    json_type = "boolean"
                else:
                    json_type = "string"

                input_schema["properties"][param_name] = {
                    "type": json_type,
                    "description": param_name
                }

                if param.default == inspect.Parameter.empty:
                    input_schema["required"].append(param_name)
        else:
            # 第三方 BaseTool 实例（如 DuckDuckGoSearchResults）：从 args schema 提取
            for arg_name, arg_spec in (tool.args or {}).items():
                input_schema["properties"][arg_name] = {
                    "type": arg_spec.get("type", "string"),
                    "description": arg_spec.get("title", arg_name)
                }
                input_schema["required"].append(arg_name)

        # Get description
        description = tool.description or tool.name

        return {
            "name": tool.name,
            "description": description,
            "function_name": func.__name__ if func is not None else tool.name,
            "input_schema": input_schema,
            "output_schema": {
                "type": "object",
                "description": "Tool execution result"
            },
            "example": self._generate_example(tool, input_schema),
            "status": "enabled"
        }
    
    def _generate_example(self, tool: BaseTool, input_schema: Dict[str, Any]) -> str:
        """Generate example usage for the tool."""
        if tool.name == "generate_chart":
            return '{"chart_type": "line", "x": "1月,2月,3月", "y": "100,200,150", "title": "销售趋势"}'
        elif tool.name == "duckduckgo_search":
            return '{"query": "Python FastAPI tutorial"}'
        elif tool.name == "ask_human":
            return '{"question": "What is your name?"}'
        elif tool.name == "calculator":
            return '{"expression": "(3 + 5) * 12 / 2"}'
        elif tool.name == "document_search":
            return '{"query": "入职满一年有几天年假"}'
        else:
            return "{}"

    async def initialize_tools(self) -> Dict[str, Any]:
        """Initialize all tools from LangGraph tools directory."""
        tools_to_register = [
            generate_chart,
            duckduckgo_search_tool,
            ask_human,
            calculator,
            document_search,
        ]
        
        results = {
            "success": [],
            "failed": [],
            "skipped": []
        }
        
        for tool in tools_to_register:
            try:
                # 先查重：已注册的直接跳过（部分工具实例无 func 属性，无法提取 schema）
                existing_tool = await self.agent_service.get_tool_by_name(tool.name)

                if existing_tool:
                    results["skipped"].append({
                        "name": tool.name,
                        "reason": "Already exists"
                    })
                    continue

                tool_schema = self.get_tool_schema(tool)

                # Create tool in database
                await self.agent_service.create_tool(tool_schema)
                results["success"].append(tool_schema["name"])
                
            except Exception as e:
                results["failed"].append({
                    "name": tool.name if hasattr(tool, 'name') else 'unknown',
                    "error": str(e)
                })
        
        return results
    
    async def get_all_langgraph_tools(self) -> list:
        """Get all available LangGraph tools."""
        return [
            generate_chart,
            duckduckgo_search_tool,
            ask_human,
            calculator,
            document_search,
        ]


# CLI command to initialize tools
async def init_tools_command():
    """Command to initialize tools."""
    initializer = ToolInitializer()
    results = await initializer.initialize_tools()
    
    print("工具初始化结果：")
    print(f"成功: {len(results['success'])}")
    for name in results['success']:
        print(f"  - {name}")
    
    print(f"跳过: {len(results['skipped'])}")
    for item in results['skipped']:
        print(f"  - {item['name']}: {item['reason']}")
    
    print(f"失败: {len(results['failed'])}")
    for item in results['failed']:
        print(f"  - {item['name']}: {item['error']}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(init_tools_command())