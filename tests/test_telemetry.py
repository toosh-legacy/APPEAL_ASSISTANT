from appeal_core.telemetry import span, trace_carrier


def test_trace_context_propagates_through_job_payload():
    with span("api.create_case", case_id="c1") as parent:
        carrier = trace_carrier()
        parent_trace = parent.get_span_context().trace_id
    assert "traceparent" in carrier
    # the worker, in another process, continues the same trace from the job payload
    with span("job.case.ingest", carrier=carrier) as child:
        assert child.get_span_context().trace_id == parent_trace
        with span("agent.intake") as grandchild:
            assert grandchild.get_span_context().trace_id == parent_trace
