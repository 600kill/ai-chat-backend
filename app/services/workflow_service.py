"""Workflow visualization service for LangGraph."""

from typing import Dict, Any, List
from uuid import UUID

from app.services.database import database_service
from app.services.agent_service import AgentService
from app.core.logging import logger


class WorkflowService:
    """Service for parsing and visualizing LangGraph workflows."""
    
    def __init__(self):
        self.agent_service = AgentService(database_service.get_session_maker())
    
    async def get_workflow_data(self, agent_id: UUID) -> Dict[str, Any]:
        """Get workflow visualization data for an agent."""
        agent = await self.agent_service.get_agent(agent_id)
        if not agent:
            raise ValueError("Agent not found")
        
        if not agent.graph_config:
            return {
                "agent_id": str(agent_id),
                "mermaid_code": "",
                "nodes": [],
                "edges": []
            }
        
        # Parse graph config and generate Mermaid code
        mermaid_code, nodes, edges = self._parse_graph_config(agent.graph_config)
        
        return {
            "agent_id": str(agent_id),
            "mermaid_code": mermaid_code,
            "nodes": nodes,
            "edges": edges
        }
    
    def _parse_graph_config(self, config: Dict[str, Any]) -> tuple[str, List[Dict], List[Dict]]:
        """Parse LangGraph config and generate Mermaid code."""
        graph_type = config.get("type", "state_graph")
        nodes = config.get("nodes", [])
        edges = config.get("edges", [])
        
        # Generate Mermaid code
        if graph_type == "state_graph":
            mermaid_code = self._generate_state_graph_mermaid(nodes, edges)
        else:
            mermaid_code = self._generate_simple_graph_mermaid(nodes, edges)
        
        return mermaid_code, nodes, edges
    
    def _generate_state_graph_mermaid(self, nodes: List[Dict], edges: List[Dict]) -> str:
        """Generate Mermaid code for state graph."""
        lines = ["graph TD"]
        
        # Add nodes
        node_styles = {
            "start": "([开始])",
            "end": "([结束])",
            "action": "[动作]",
            "tool": "{{工具}}",
            "decision": "{判断}",
            "think": "(思考)"
        }
        
        node_id_map = {}
        for idx, node in enumerate(nodes):
            node_id = f"node{idx}"
            node_id_map[node.get("id", idx)] = node_id
            node_type = node.get("type", "action")
            style = node_styles.get(node_type, "[节点]")
            
            label = node.get("label", node.get("name", f"Node {idx}"))
            node_label = style.replace('动作', f'[{label}]').replace('工具', f'{{{label}}}').replace('判断', f'{{{label}}}').replace('思考', f'({label})')
            lines.append(f"    {node_id}{node_label}")
        
        # Add edges
        for edge in edges:
            from_id = edge.get("from")
            to_id = edge.get("to")
            condition = edge.get("condition")
            
            if from_id in node_id_map and to_id in node_id_map:
                edge_str = f"    {node_id_map[from_id]} --> {node_id_map[to_id]}"
                if condition:
                    edge_str += f" |{condition}|"
                lines.append(edge_str)
        
        return "\n".join(lines)
    
    def _generate_simple_graph_mermaid(self, nodes: List[Dict], edges: List[Dict]) -> str:
        """Generate Mermaid code for simple graph."""
        lines = ["graph LR"]
        
        for idx, node in enumerate(nodes):
            lines.append(f"    node{idx}[{node.get('name', f'Node {idx}')}]")
        
        for edge in edges:
            lines.append(f"    node{edge.get('from')} --> node{edge.get('to')}")
        
        return "\n".join(lines)
    
    async def create_default_graph_config(self) -> Dict[str, Any]:
        """Create a default graph config for new agents."""
        return {
            "type": "state_graph",
            "nodes": [
                {"id": "start", "type": "start", "label": "开始"},
                {"id": "think", "type": "think", "label": "思考"},
                {"id": "action", "type": "action", "label": "执行"},
                {"id": "end", "type": "end", "label": "结束"}
            ],
            "edges": [
                {"from": "start", "to": "think"},
                {"from": "think", "to": "action"},
                {"from": "action", "to": "end"}
            ]
        }


# Global instance
workflow_service = WorkflowService()