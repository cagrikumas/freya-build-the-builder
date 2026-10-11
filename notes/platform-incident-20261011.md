# Conversation startup failures — 11 October 2026

Observed in the staging workspace during public practice, before the final case
opened. This is evidence of a shared conversation-service problem; the exact
upstream cause has not been confirmed.

- Workspace: `f22d7c29-2569-4a74-b8fc-b626c80454a5`.
- Simulation `8f7a101d-2535-4e00-aa72-a24e634c196d`: ten calls finished with no
  first assistant message and no bank tool calls. No completed judge verdicts
  were available when scored. The dashboard displayed 0%.
- Example call `deb0f9b4-c991-4f6a-977b-1f973d943b33`: only the initial
  `node_enter identity` event, no conversation, approximately 60-second duration.
- Direct `POST /api/v2/chat/message` returned HTTP 504 for the new practice A
  workflow and for the previously working practice B workflow.
- A later control with the untouched **Freya Bank Collections Base** workflow
  `4485fd11-01ee-43ae-8130-60490035a1ed` also returned HTTP 504. Result recorded
  at approximately 15:35 UTC / 18:35 Istanbul.
- The base workflow's provider/model are both `experimental-5`, the event model.
- Authenticated workflow reads and workflow validation/save requests respond;
  the account has sufficient credits.

No retry loop or load test was run. Broad simulations were stopped after the
startup failures; only targeted single-turn controls were attempted. No bank
operation was requested by those opening messages. No incident email has been
sent from this workspace.
