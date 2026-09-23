"""Integration tests for MetricsService using real database."""

import pytest
import uuid
from datetime import datetime

from app.services.metrics_service import MetricsService
from app.models.session import Session as ChatSession


class TestMetricsService:
    """Test cases for MetricsService with real database."""

    @pytest.mark.asyncio
    async def test_start_session(self, db_session, test_agent, test_user):
        """Test start_session method creates a new metrics session."""
        service = MetricsService()
        session_id = str(uuid.uuid4())
        
        chat_session = ChatSession(id=session_id, user_id=test_user.id, name="Test Session")
        db_session.add(chat_session)
        db_session.commit()
        
        metrics_session_id = await service.start_session(session_id, test_agent.id, test_user.id)
        
        assert isinstance(metrics_session_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_end_session(self, db_session, test_agent, test_user):
        """Test end_session method updates session metrics."""
        service = MetricsService()
        session_id = str(uuid.uuid4())
        
        chat_session = ChatSession(id=session_id, user_id=test_user.id, name="Test Session")
        db_session.add(chat_session)
        db_session.commit()
        
        metrics_session_id = await service.start_session(session_id, test_agent.id, test_user.id)
        
        await service.end_session(
            metrics_session_id=metrics_session_id,
            total_duration_ms=5000,
            status="success"
        )
        
        session_metrics = await service.get_session_metrics(session_id)
        assert session_metrics is not None
        assert session_metrics.total_duration_ms == 5000
        assert session_metrics.status == "success"
        assert session_metrics.ended_at is not None

    @pytest.mark.asyncio
    async def test_record_llm_inference(self, db_session, test_agent, test_user):
        """Test record_llm_inference method records LLM metrics."""
        service = MetricsService()
        session_id = str(uuid.uuid4())
        
        chat_session = ChatSession(id=session_id, user_id=test_user.id, name="Test Session")
        db_session.add(chat_session)
        db_session.commit()
        
        metrics_session_id = await service.start_session(session_id, test_agent.id, test_user.id)
        
        await service.record_llm_inference(
            metrics_session_id=metrics_session_id,
            session_id=session_id,
            llm_model="qwen-turbo",
            inference_duration_ms=3500,
            input_tokens=500,
            output_tokens=200,
            total_tokens=700,
            ttft_ms=150,
            token_cost=0.0021
        )
        
        full_trace = await service.get_session_full_trace(session_id)
        assert full_trace is not None
        assert full_trace["llm_metrics"] is not None
        assert full_trace["llm_metrics"]["llm_model"] == "qwen-turbo"
        assert full_trace["llm_metrics"]["input_tokens"] == 500

    @pytest.mark.asyncio
    async def test_record_vector_search(self, db_session, test_agent, test_user):
        """Test record_vector_search method records vector search metrics."""
        service = MetricsService()
        session_id = str(uuid.uuid4())
        
        chat_session = ChatSession(id=session_id, user_id=test_user.id, name="Test Session")
        db_session.add(chat_session)
        db_session.commit()
        
        metrics_session_id = await service.start_session(session_id, test_agent.id, test_user.id)
        
        await service.record_vector_search(
            metrics_session_id=metrics_session_id,
            session_id=session_id,
            search_duration_ms=50,
            results_count=3,
            memory_type="long_term"
        )
        
        full_trace = await service.get_session_full_trace(session_id)
        assert full_trace is not None
        assert len(full_trace["vector_metrics"]) == 1
        assert full_trace["vector_metrics"][0]["search_duration_ms"] == 50

    @pytest.mark.asyncio
    async def test_record_tool_call(self, db_session, test_agent, test_user):
        """Test record_tool_call method records tool call metrics."""
        service = MetricsService()
        session_id = str(uuid.uuid4())
        
        chat_session = ChatSession(id=session_id, user_id=test_user.id, name="Test Session")
        db_session.add(chat_session)
        db_session.commit()
        
        metrics_session_id = await service.start_session(session_id, test_agent.id, test_user.id)
        
        await service.record_tool_call(
            metrics_session_id=metrics_session_id,
            session_id=session_id,
            tool_name="generate_chart",
            call_duration_ms=800,
            input_params={"query": "test"}
        )
        
        full_trace = await service.get_session_full_trace(session_id)
        assert full_trace is not None
        assert len(full_trace["tool_metrics"]) == 1
        assert full_trace["tool_metrics"][0]["tool_name"] == "generate_chart"

    @pytest.mark.asyncio
    async def test_record_node_execution(self, db_session, test_agent, test_user):
        """Test record_node_execution method records node execution metrics."""
        service = MetricsService()
        session_id = str(uuid.uuid4())
        
        chat_session = ChatSession(id=session_id, user_id=test_user.id, name="Test Session")
        db_session.add(chat_session)
        db_session.commit()
        
        metrics_session_id = await service.start_session(session_id, test_agent.id, test_user.id)
        
        await service.record_node_execution(
            metrics_session_id=metrics_session_id,
            session_id=session_id,
            node_name="chat",
            node_type="chat",
            duration_ms=3800
        )
        
        full_trace = await service.get_session_full_trace(session_id)
        assert full_trace is not None
        assert len(full_trace["node_metrics"]) == 1
        assert full_trace["node_metrics"][0]["node_name"] == "chat"

    @pytest.mark.asyncio
    async def test_record_node_execution_order(self, db_session, test_agent, test_user):
        """Test that node execution order increments correctly."""
        service = MetricsService()
        session_id = str(uuid.uuid4())
        
        chat_session = ChatSession(id=session_id, user_id=test_user.id, name="Test Session")
        db_session.add(chat_session)
        db_session.commit()
        
        metrics_session_id = await service.start_session(session_id, test_agent.id, test_user.id)
        
        await service.record_node_execution(
            metrics_session_id=metrics_session_id,
            session_id=session_id,
            node_name="chat",
            node_type="chat",
            duration_ms=1000
        )
        
        await service.record_node_execution(
            metrics_session_id=metrics_session_id,
            session_id=session_id,
            node_name="tool_call",
            node_type="tool_call",
            duration_ms=2000
        )
        
        full_trace = await service.get_session_full_trace(session_id)
        assert len(full_trace["node_metrics"]) == 2
        assert full_trace["node_metrics"][0]["execution_order"] == 1
        assert full_trace["node_metrics"][1]["execution_order"] == 2

    def test_percentile_calculation(self):
        """Test percentile calculation algorithm."""
        service = MetricsService()
        
        data = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
        
        p50 = service._percentile(data, 0.50)
        p90 = service._percentile(data, 0.90)
        p95 = service._percentile(data, 0.95)
        p99 = service._percentile(data, 0.99)
        
        assert p50 == 550.0
        assert p90 == 910.0
        assert abs(p95 - 955.0) < 0.01
        assert abs(p99 - 991.0) < 0.01

    def test_percentile_empty_list(self):
        """Test percentile calculation with empty list."""
        service = MetricsService()
        
        result = service._percentile([], 0.50)
        
        assert result == 0.0

    def test_percentile_single_element(self):
        """Test percentile calculation with single element."""
        service = MetricsService()
        
        result = service._percentile([500], 0.90)
        
        assert result == 500

    @pytest.mark.asyncio
    async def test_calculate_latency_percentiles(self, db_session, test_agent, test_user):
        """Test calculate_latency_percentiles method."""
        service = MetricsService()
        
        for i in range(5):
            session_id = str(uuid.uuid4())
            chat_session = ChatSession(id=session_id, user_id=test_user.id, name=f"Test Session {i}")
            db_session.add(chat_session)
            db_session.commit()
            
            metrics_session_id = await service.start_session(session_id, test_agent.id, test_user.id)
            await service.end_session(
                metrics_session_id=metrics_session_id,
                total_duration_ms=(i + 1) * 1000,
                status="success"
            )
        
        result = await service.calculate_latency_percentiles(agent_id=test_agent.id)
        
        assert result["total_sessions"] == 5
        assert result["avg_duration_ms"] == 3000
        assert "p50_latency_ms" in result
        assert "p90_latency_ms" in result
        assert "p99_latency_ms" in result

    @pytest.mark.asyncio
    async def test_calculate_latency_percentiles_empty(self):
        """Test calculate_latency_percentiles with no data."""
        service = MetricsService()
        
        result = await service.calculate_latency_percentiles(agent_id=uuid.uuid4())
        
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_session_list(self, db_session, test_agent, test_user):
        """Test get_session_list method."""
        service = MetricsService()
        
        for i in range(3):
            session_id = str(uuid.uuid4())
            chat_session = ChatSession(id=session_id, user_id=test_user.id, name=f"Test Session {i}")
            db_session.add(chat_session)
            db_session.commit()
            
            metrics_session_id = await service.start_session(session_id, test_agent.id, test_user.id)
            await service.end_session(
                metrics_session_id=metrics_session_id,
                total_duration_ms=1000,
                status="success"
            )
        
        result = await service.get_session_list(agent_id=test_agent.id, page=1, size=20)
        
        assert result["total"] >= 3
        assert len(result["items"]) >= 3

    @pytest.mark.asyncio
    async def test_get_session_full_trace(self, db_session, test_agent, test_user):
        """Test get_session_full_trace method."""
        service = MetricsService()
        session_id = str(uuid.uuid4())
        
        chat_session = ChatSession(id=session_id, user_id=test_user.id, name="Test Session")
        db_session.add(chat_session)
        db_session.commit()
        
        metrics_session_id = await service.start_session(session_id, test_agent.id, test_user.id)
        
        await service.record_llm_inference(
            metrics_session_id=metrics_session_id,
            session_id=session_id,
            llm_model="qwen-turbo",
            inference_duration_ms=2000,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150
        )
        
        await service.end_session(
            metrics_session_id=metrics_session_id,
            total_duration_ms=3000,
            status="success"
        )
        
        trace = await service.get_session_full_trace(session_id)
        
        assert trace is not None
        assert trace["session_info"]["session_id"] == session_id
        assert trace["session_info"]["agent_id"] == str(test_agent.id)
        assert trace["session_info"]["user_id"] == test_user.id
        assert trace["llm_metrics"] is not None

    @pytest.mark.asyncio
    async def test_get_session_full_trace_not_found(self):
        """Test get_session_full_trace returns None for non-existent session."""
        service = MetricsService()
        
        trace = await service.get_session_full_trace("nonexistent-session")
        
        assert trace is None

    @pytest.mark.asyncio
    async def test_get_agent_stats(self, db_session, test_agent, test_user):
        """Test get_agent_stats method."""
        service = MetricsService()
        
        for i in range(3):
            session_id = str(uuid.uuid4())
            chat_session = ChatSession(id=session_id, user_id=test_user.id, name=f"Test Session {i}")
            db_session.add(chat_session)
            db_session.commit()
            
            metrics_session_id = await service.start_session(session_id, test_agent.id, test_user.id)
            await service.record_llm_inference(
                metrics_session_id=metrics_session_id,
                session_id=session_id,
                llm_model="qwen-turbo",
                inference_duration_ms=1000,
                input_tokens=100,
                output_tokens=50,
                total_tokens=150
            )
            await service.end_session(
                metrics_session_id=metrics_session_id,
                total_duration_ms=2000,
                status="success"
            )
        
        stats = await service.get_agent_stats(agent_id=test_agent.id)
        
        assert stats["agent_id"] == str(test_agent.id)
        assert stats["agent_name"] == test_agent.name
        assert stats["session_stats"]["total_sessions"] >= 3
        assert stats["token_stats"]["total_tokens"] >= 450

    @pytest.mark.asyncio
    async def test_get_concurrent_stats(self, db_session, test_agent, test_user):
        """Test get_concurrent_stats method."""
        service = MetricsService()
        
        session_id = str(uuid.uuid4())
        chat_session = ChatSession(id=session_id, user_id=test_user.id, name="Test Session")
        db_session.add(chat_session)
        db_session.commit()
        
        await service.start_session(session_id, test_agent.id, test_user.id)
        
        stats = await service.get_concurrent_stats(agent_id=test_agent.id)
        
        assert "current" in stats
        assert "history" in stats

    @pytest.mark.asyncio
    async def test_get_daily_token_summary(self, db_session, test_agent, test_user):
        """Test get_daily_token_summary method."""
        service = MetricsService()
        
        session_id = str(uuid.uuid4())
        chat_session = ChatSession(id=session_id, user_id=test_user.id, name="Test Session")
        db_session.add(chat_session)
        db_session.commit()
        
        metrics_session_id = await service.start_session(session_id, test_agent.id, test_user.id)
        await service.record_llm_inference(
            metrics_session_id=metrics_session_id,
            session_id=session_id,
            llm_model="qwen-turbo",
            inference_duration_ms=1000,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            token_cost=0.001
        )
        await service.end_session(
            metrics_session_id=metrics_session_id,
            total_duration_ms=2000,
            status="success"
        )
        
        summary = await service.get_daily_token_summary(agent_id=test_agent.id)
        
        assert "items" in summary
        assert "total" in summary

    @pytest.mark.asyncio
    async def test_get_token_allocation(self, db_session, test_agent, test_user):
        """Test get_token_allocation method."""
        service = MetricsService()
        
        session_id = str(uuid.uuid4())
        chat_session = ChatSession(id=session_id, user_id=test_user.id, name="Test Session")
        db_session.add(chat_session)
        db_session.commit()
        
        metrics_session_id = await service.start_session(session_id, test_agent.id, test_user.id)
        await service.record_llm_inference(
            metrics_session_id=metrics_session_id,
            session_id=session_id,
            llm_model="qwen-turbo",
            inference_duration_ms=1000,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            token_cost=0.001
        )
        await service.end_session(
            metrics_session_id=metrics_session_id,
            total_duration_ms=2000,
            status="success"
        )
        
        allocation = await service.get_token_allocation(group_by="agent")
        
        assert "total_cost" in allocation
        assert "allocations" in allocation

    def test_clear_execution_order(self):
        """Test _clear_execution_order method."""
        service = MetricsService()
        
        session_id = "test-session"
        service._execution_order_cache[session_id] = 5
        
        service._clear_execution_order(session_id)
        
        assert session_id not in service._execution_order_cache


if __name__ == "__main__":
    pytest.main([__file__, "-v"])