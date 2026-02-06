VERDICT: Solid scope, but has ~6 issues that would cause GPT to produce broken code, plus ~8 ambiguities that need tightening.

CRITICAL — Will Break If Not Fixed
1. Topic Generation Token Collision (Section 5)
The spec connects ctx.guard.sig_token.connect(self._on_title_token) for title generation. But sig_token is a global signal — it fires for every token from every generation. There's no way to distinguish title tokens from chat tokens. When a title generation runs, chat tokens would also hit _on_title_token. When a chat generation runs after title gen was wired, those tokens also hit the title handler.
You need one of: a task-aware token routing mechanism, a separate signal per task, or at minimum a guard flag like self._awaiting_title = True that gates the handler. This is the biggest bug in the spec.
2. Topic Generation Can't Fire Mid-Generation (Section 5)
The spec triggers title gen when _session_token_count >= 250, which happens during an active generation. But the kernel enforces one active Task per engine. The title gen task (priority 3) can't submit to the LLM while chat generation is RUNNING — guard.submit() returns False.
The spec needs to clarify: title generation queues in MonoDock and runs after the current generation completes. But then the token count check in append_token() needs to set a flag and defer, not call _generate_initial_title() immediately.
3. HUB Routes to Non-Existent "system" Engine (Section 6.2)
pythonctx.bridge.wrap("hub", "load_operator", "system", payload={"operator": operator_name})
There's no "system" engine registered in MonoGuard. ENGINE_DISPATCH only has set_path, load, unload, generate. This task would fail at guard.submit() — no engine, no dispatch method.
Operator loading is a UI-layer concern, not an engine operation. The HUB should call OperatorManager directly, not route through the kernel. Remove this from the kernel pipeline entirely.
4. QListWidget Migration — Token Streaming Unspecified (Section 3.3)
Migrating from QTextEdit to QListWidget fundamentally changes how token streaming works. Currently append_token() appends text to a QTextEdit cursor position character by character. With QListWidget + MessageWidget (which uses QLabel), you need to accumulate tokens into the last QLabel widget in the list and update it incrementally.
The spec never defines this new append_token() for the QListWidget world. GPT will either break streaming entirely or revert to QTextEdit patterns. This needs an explicit streaming pattern for the new architecture.
5. Conversation History Sync Has No Kernel Path (Section 3.4-3.6)
The spec calls self._update_llm_conversation_history() after edits/deletes, but PageChat can't directly access LLMEngine.conversation_history — that would violate the kernel contract (UI must not call engines directly).
There's no task command defined for "sync conversation history" or "set conversation history". You need either: a new kernel command ("set_history" in ENGINE_DISPATCH), or the approach where PageChat owns the history and passes it in the generate payload every time (which the current architecture partially does via payload["prompt"] but not for full history manipulation).
6. Delete Cascade Uses Fragile Timer Retry (Section 3.5)
pythonQTimer.singleShot(100, lambda: self._delete_message_cascade(start_index))
100ms is arbitrary and may not be enough for the engine to reach READY after STOP. This should connect to sig_engine_ready instead of polling with a timer.

IMPORTANT — Ambiguities GPT Will Resolve Incorrectly
7. Operator vs Config Precedence Undefined (Sections 1 & 6)
Two config hierarchies overlap:

Config: DEFAULT → llm.json → session → user save
Operator: DEFAULT → operator.json → session → disk

What wins when an operator says temp=0.3 but the saved llm.json says temp=0.7? The spec needs an explicit rule: does loading an operator replace the session config, or merge with it?
8. GGUF Metadata — Three Options, No Decision (Section 1.3)
The spec gives Options A, B, and C for reading GGUF context length but doesn't commit. GPT will pick one arbitrarily. Decide now — llama-cpp-python is already a dependency, so Option A is the natural choice, but the spec needs to say so.
9. Thinking Mode Backend Undefined (Section 2.2)
The toggle stores self._thinking_mode but "Backend implementation TBD." What config field does this map to? A behavior tag? A new payload key? A separate config value? If undefined, GPT will invent something that may conflict with the behavior tag system.
10. Hardcoded Windows Paths (Throughout)
C:\Monolith\ is hardcoded everywhere. This breaks if you ever want cross-platform or even a different drive. Should be a single constant, ideally Path.home() / "Monolith" or at minimum MONOLITH_ROOT = Path("C:/Monolith") defined once and referenced everywhere.
11. OperatorManager Accesses Private AddonHost State (Section 6.5)
pythonfor addon_id, instance in ui.host._instances.items():
_instances is private. If AddonHost changes internally, this breaks silently. Either make it public (instances or get_instances()) or add a host.capture_state() method.
12. Overseer Creates New DB Connection Every 500ms (Section 7.3)
_poll_logs instantiates OverseerDB(...) on every poll. That's a new SQLite connection every half second. Should be self.db = OverseerDB(...) in __init__ and reused.
13. Overseer Exemption From Addon System Unstated
The Overseer is a standalone QMainWindow, not an addon. This is architecturally fine for debug tooling, but the spec should explicitly state why so GPT doesn't try to "fix" it by making it an addon.
14. sig_update Signal Not Declared (Section 3.6)
The regen feature references self.sig_update and shows builtin.py wiring, but never shows the signal declaration in PageChat. GPT needs to see sig_update = Signal(str) in the class definition.

MINOR — Nice to Fix

The _topic_dominant relaxation (Section 4.3) changes from 3+ to 2+ occurrences but doesn't address the core issue: 4-letter minimum excludes common topic words like "AI", "API", "bug". Consider a stopword approach instead.
Operator names as filenames ({name}.json) will break with special characters. Need sanitization.
The spec mentions files.py (Databank addon) in the directory structure but it's absent from architecture.md. New addition?
