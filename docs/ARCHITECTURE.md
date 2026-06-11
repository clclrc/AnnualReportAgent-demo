# Architecture Notes

This public demo keeps the project close to its original engineering shape so reviewers can see the real system boundaries.

## Request Flow

1. `service_api.py` receives a question.
2. `api_llm.py` builds runtime artifacts:
   - question classification
   - keyword extraction
   - optional NL2SQL generation
3. `financial_agent_workflow.py` builds a route-aware `QuestionContext`.
4. The workflow dispatches to one of three main execution styles:
   - structured table lookup
   - SQL / aggregation over `company_table`
   - open-text synthesis from annual report snippets
5. The workflow returns:
   - final answer
   - evidence items
   - route trace
   - timing metadata

## Public Demo Boundary

The original private project included full PDF data, preprocessing checkpoints, and larger experiment archives. This demo intentionally keeps only:

- extracted structured tables
- stored classify / keyword / SQL / answer artifacts
- one small report slice for open-question evidence replay
- benchmark summaries and regression cases

That keeps the repo public-safe while still showing the system is real, routed, and measurable.
