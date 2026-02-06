# MONOLITH ARCHITECTURAL SPECIFICATION
**Target Audience:** GPT-4 / AI Code Generators  
**Purpose:** Complete implementation guide for Monolith improvements  
**Revision:** v1.0  
**Date:** 2025-02-05

---

## KEY IMPLEMENTATION DECISIONS

**Storage Architecture:**
- **Operator Configs**: JSON files (human-readable, version control friendly)
- **Overseer Logs**: SQLite database (queryable, filterable, high volume)
- **Addon Configs**: Consolidated to `C:\Monolith\config\addons\`

**Message Actions:**
- **QListWidget migration** recommended for structure (real objects vs HTML parsing)
- **Undo/Redo**: Terminal input field only (Qt built-in), NOT full message history

**Performance Optimizations:**
- **Viztracer pre-filtering**: Reduces overhead from ~10% to ~2-3%
  - `min_duration=5000` (>5ms only)
  - `ignore_frozen=True` (skip stdlib)
  - `exclude_files=["site-packages"]` (skip deps)
  - Cuts log noise by ~80%

**Config Path Consolidation:**
- All configs moved to `C:\Monolith\` (was scattered in `C:\Models\llama_env\`)
- Legacy migration logic for smooth transition

**Log Retention:**
- 10 sessions (viztracer JSON dumps)
- SQLite database persists indefinitely with queryable history

---

## TABLE OF CONTENTS

1. [System Context](#system-context)
2. [Config System Overhaul](#1-config-system-overhaul)
3. [Terminal UI Improvements](#2-terminal-ui-improvements)
   - 2.1 Generation Status Right-Alignment
   - 2.2 Input Bar Enhancements
   - 2.3 Date/Time Display (Terminal Only)
   - 2.4 Operations Panel Restructuring
4. [Message Actions System](#3-message-actions-system)
5. [Bug Fixes](#4-bug-fixes)
6. [Topic Generation](#5-topic-generation)
7. [Operator System + HUB Landing Page](#6-operator-system--hub-landing-page)
8. [Overseer Debug Interface](#7-overseer-debug-interface)
9. [Implementation Order](#8-implementation-order)

---

## SYSTEM CONTEXT

### Kernel Contract v2 (FROZEN)
All components must follow Kernel Contract v2:

**Authority Hierarchy:**
```
UI → MonoBridge → MonoDock → MonoGuard → Engines
```

**Three Flows:**
- **Commands**: Downward (UI → Engine)
- **State**: Upward (Engine → UI)
- **STOP**: Instant bypass

**Critical Rules:**
- UI never calls engines directly
- All execution goes through MonoGuard
- Engines know nothing about UI/Kernel
- One active Task per engine
- STOP always wins (priority 1)

### Addon System
Two addon types:
1. **Page addons** (`kind="page"`): Full-screen in main content area
2. **Module addons** (`kind="module"`): Stackable floating modules

**AddonSpec Structure:**
```python
@dataclass(frozen=True)
class AddonSpec:
    id: str                                    # e.g., "terminal", "hub"
    kind: Literal["page", "module"]           
    title: str                                # Display name
    icon: str | None                          # Unicode icon
    factory: Callable[[AddonContext], QWidget]
```

**AddonContext (Dependency Injection):**
```python
@dataclass
class AddonContext:
    state: AppState        # Shared app state
    guard: MonoGuard       # Signal router
    bridge: MonoBridge     # Task submission
    ui: MonolithUI | None  # Main window
    host: AddonHost | None # Addon lifecycle
```

### Current Directory Structure
```
monolith-main/
├── monokernel/
│   ├── guard.py
│   ├── dock.py
│   └── bridge.py
├── engine/
│   ├── llm.py
│   └── vision.py
├── ui/
│   ├── main_window.py
│   ├── pages/
│   │   ├── chat.py      # Terminal addon
│   │   └── files.py     # Databank addon
│   ├── modules/
│   │   ├── sd.py        # Vision module
│   │   └── injector.py  # Context injector
│   └── addons/
│       ├── spec.py
│       ├── registry.py
│       ├── host.py
│       └── builtin.py
├── core/
│   ├── state.py
│   ├── task.py
│   └── llm_config.py
└── bootstrap.py

C:/Monolith/              # NEW: Consolidated config/data directory
├── config/
│   ├── addons/          # NEW: All addon configs
│   │   ├── llm.json
│   │   ├── vision.json
│   │   └── audio.json
│   ├── operators/       # NEW: Operator presets
│   │   └── *.json
│   └── logs/            # NEW: Overseer logs
│       ├── overseer.db  # SQLite for queryable logs
│       └── trace_*.json # Viztracer session dumps
├── models/              # OPTIONAL: User model storage
└── outputs/             # Generated content
    ├── images/
    └── audio/
```

---

## 1. CONFIG SYSTEM OVERHAUL

### 1.1 Problem Statement

**Current Issues:**
1. Config auto-saves on every slider change (performance hit)
2. Model capability clamps overwrite user config values
3. No distinction between "user change" vs "computer change"
4. `context_injection` field is deprecated but still in config

**Current Flow:**
```
User moves slider → _update_config_value() → save_config() → Disk write
Model loads → _on_model_capabilities() → Overwrite slider value → save_config()
```

### 1.2 Solution Architecture

#### Base Config (Immutable Default)
**Location:** Hardcoded in `core/llm_config.py`

```python
DEFAULT_CONFIG = {
    "gguf_path": None,
    "temp": 0.7,
    "top_p": 0.9,
    "max_tokens": 2048,
    "ctx_limit": 8192,
    "system_prompt": MASTER_PROMPT,  # Always forced, never saved
    "behavior_tags": [],
    # context_injection REMOVED
}
```

#### Session Config (In-Memory Active State)
**Location:** `PageChat.config` dictionary  
**Behavior:** 
- Loaded from disk on Terminal addon initialization
- Modified by user interactions
- Clamped by model capabilities (without saving clamps)
- Only explicitly saved when user clicks "Save"

#### User Change Detection
**Implementation Strategy:** UI event-based detection

**Method 1 (Preferred):** Event-driven tracking
```python
# In PageChat.__init__
self._user_modified_fields = set()  # Track which fields user touched

# Connect to slider valueChanged with tracking
self.s_temp.valueChanged.connect(
    lambda v: self._on_user_slider_change("temp", v)
)

def _on_user_slider_change(self, key, value):
    self._user_modified_fields.add(key)
    self.config[key] = value
    # NO auto-save here
```

**Method 2 (Fallback):** Signal-based detection
```python
# Track whether change originated from UI interaction
self._is_programmatic_change = False

def _set_slider_value_programmatically(self, slider, value):
    self._is_programmatic_change = True
    slider.setValue(value)
    self._is_programmatic_change = False

def _on_slider_changed(self, key, value):
    if not self._is_programmatic_change:
        self._user_modified_fields.add(key)
    self.config[key] = value
```

### 1.3 Model Validation Flow

**Objective:** Read GGUF metadata without loading model to validate config

**Implementation:**
1. Use `llama-cpp-python` or `gguf-parser` library to read GGUF header
2. Extract `context_length` from metadata
3. Clamp session config in-memory only

**Code Pattern:**
```python
def _validate_config_against_model(self, gguf_path: str):
    """Read GGUF metadata and clamp config without saving"""
    if not gguf_path or not os.path.exists(gguf_path):
        return
    
    # Read GGUF header (non-blocking, fast)
    model_ctx_length = self._read_gguf_context_length(gguf_path)
    
    if model_ctx_length is None:
        return
    
    # Clamp session config in-memory (computer change)
    user_ctx = self.config.get("ctx_limit", 8192)
    user_tok = self.config.get("max_tokens", 2048)
    
    clamped_ctx = min(user_ctx, model_ctx_length)
    clamped_tok = min(user_tok, model_ctx_length)
    
    # Update session config (NOT saved to disk)
    self.config["ctx_limit"] = clamped_ctx
    self.config["max_tokens"] = clamped_tok
    
    # Update slider bounds without triggering save
    self._set_slider_limits_programmatically(
        self.s_ctx, model_ctx_length, clamped_ctx
    )
    self._set_slider_limits_programmatically(
        self.s_tok, model_ctx_length, clamped_tok
    )

def _read_gguf_context_length(self, path: str) -> int | None:
    """Extract context_length from GGUF metadata without loading model"""
    try:
        # Option A: Using llama-cpp-python (if available)
        from llama_cpp import Llama
        # Read metadata only, no model load
        # Implementation depends on library capabilities
        
        # Option B: Using gguf-parser library
        # import gguf
        # reader = gguf.GGUFReader(path)
        # metadata = reader.get_metadata()
        # return metadata.get('context_length')
        
        # Option C: Manual GGUF parsing (if needed)
        # Parse GGUF header format to extract metadata
        pass
    except Exception as e:
        return None
```

**Call Site:** Run validation when Terminal addon opens
```python
# In PageChat.__init__, after config load
self.config = load_config()
if self.config.get("gguf_path"):
    self._validate_config_against_model(self.config["gguf_path"])
```

### 1.4 UI Changes

#### Remove Auto-Save Behavior
**Current Code to Remove:**
```python
# DELETE these auto-save calls
def _update_config_value(self, key, value):
    self.config[key] = value
    self._save_config()  # ← REMOVE THIS
```

**New Pattern:**
```python
def _update_config_value(self, key, value):
    self.config[key] = value
    self._user_modified_fields.add(key)
    # No save here
```

#### Add Save/Reset Buttons
**Location:** Below behavior tags in AI CONFIGURATION groupbox

**UI Layout:**
```
AI CONFIGURATION
├── Temperature slider
├── Top-P slider
├── Max Tokens slider
├── Context Limit slider
├── Behavior Tags input
└── [Save Config] [Reset to Default]  ← NEW
```

**Button Behavior:**
- **Save Config**: Writes current `self.config` to disk
- **Reset to Default**: Resets `self.config` to `DEFAULT_CONFIG`, updates sliders

**Implementation Pattern:**
```python
# In PageChat.__init__ UI construction
btn_save = SkeetButton("SAVE CONFIG")
btn_save.clicked.connect(self._save_config)

btn_reset = SkeetButton("RESET TO DEFAULT")
btn_reset.clicked.connect(self._reset_config)

config_actions = QHBoxLayout()
config_actions.addWidget(btn_save)
config_actions.addWidget(btn_reset)
grp_ai.add_layout(config_actions)

def _save_config(self):
    save_config(self.config)  # Write to disk
    self._user_modified_fields.clear()
    # Show feedback
    
def _reset_config(self):
    self.config = DEFAULT_CONFIG.copy()
    self._user_modified_fields.clear()
    # Update all sliders to default values
    self._update_sliders_from_config()
```

### 1.5 Config File Changes

**Remove Deprecated Fields:**
```python
# In load_config()
def load_config():
    config = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                if isinstance(data, dict):
                    # Remove deprecated fields
                    data.pop("context_injection", None)  # ← Already exists
                    data.pop("system_prompt", None)      # ← Already exists
                    config.update(data)
        except Exception:
            pass
    config["system_prompt"] = MASTER_PROMPT  # Always forced
    return config
```

### 1.6 Summary of Config Layers

```
┌─────────────────────────────────────┐
│   DEFAULT_CONFIG (code, immutable)  │
└──────────────┬──────────────────────┘
               │
               ↓ load_config()
┌─────────────────────────────────────┐
│  llm_config.json (disk, user saves) │
└──────────────┬──────────────────────┘
               │
               ↓ Loaded into memory
┌─────────────────────────────────────┐
│  PageChat.config (session, active)  │ ← User changes, model clamps
└──────────────┬──────────────────────┘
               │
               ↓ User clicks Save
┌─────────────────────────────────────┐
│  llm_config.json (written to disk)  │
└─────────────────────────────────────┘
```

**Change Types:**
- **User Change**: Direct UI interaction → Marks field in `_user_modified_fields` → Saves when user clicks Save
- **Computer Change**: Model validation/clamping → Updates session config only → Never saved automatically

---

## 2. TERMINAL UI IMPROVEMENTS

### 2.1 Generation Status Right-Alignment

**Current Display (Reasoning Trace panel):**
```
→ init backend: C:/Models/Models/mistral-7b.gguf
[GENERATING]
```

**Target Display:**
```
→ init backend: C:/Models/Models/mistral-7b.gguf                    [GENERATING]
                                                                    ↑ Right-aligned
```

**Implementation Strategy:**

#### Option A: QLabel with Right-Aligned Text
```python
# In Reasoning Trace panel
status_layout = QHBoxLayout()
status_layout.setContentsMargins(0, 0, 0, 0)

self.lbl_backend_path = QLabel()
self.lbl_backend_path.setWordWrap(True)  # Wrap if too long
self.lbl_backend_path.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")

self.lbl_generation_status = QLabel()
self.lbl_generation_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
self.lbl_generation_status.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 10px;")
self.lbl_generation_status.setFixedWidth(120)  # Reserve space

status_layout.addWidget(self.lbl_backend_path, 1)  # Stretch
status_layout.addWidget(self.lbl_generation_status, 0)  # Fixed

# Update methods
def _update_backend_status(self, path: str):
    self.lbl_backend_path.setText(f"→ init backend: {path}")

def _update_generation_status(self, status: str):
    self.lbl_generation_status.setText(f"[{status}]")
```

#### Option B: HTML Formatting in Single QLabel
```python
def _format_status_line(self, path: str, status: str) -> str:
    # Calculate available width
    max_width = self.width() - 150  # Reserve for status
    
    html = f"""
    <table width='100%' style='border: none;'>
        <tr>
            <td style='text-align: left;'>→ init backend: {path}</td>
            <td style='text-align: right; white-space: nowrap;'>[{status}]</td>
        </tr>
    </table>
    """
    return html
```

#### Responsive Wrapping
**Requirement:** If backend path is too long, wrap to second line

```python
def _update_status_display(self, path: str, status: str):
    # Check if text exceeds available width
    label_width = self.lbl_backend_path.width()
    font_metrics = QFontMetrics(self.lbl_backend_path.font())
    text_width = font_metrics.horizontalAdvance(f"→ init backend: {path}")
    
    if text_width > (label_width - 120):  # -120 for status width
        # Enable word wrap
        self.lbl_backend_path.setWordWrap(True)
    else:
        self.lbl_backend_path.setWordWrap(False)
    
    self.lbl_backend_path.setText(f"→ init backend: {path}")
    self.lbl_generation_status.setText(f"[{status}]")
```

### 2.2 Input Bar Enhancements

**Location:** Between the white line (above chat display) and the "Enter command" input box

**Layout:**
```
┌────────────────────────────────────────────────────────────┐
│                     TERMINAL                                │
├────────────────────────────────────────────────────────────┤
│  [Chat messages display area]                              │
│                                                             │
├────────────────────────────────────────────────────────────┤
│  [+] Actions                           [⚡] Thinking Mode   │  ← NEW BAR
├────────────────────────────────────────────────────────────┤
│  Enter command...                               [SEND]     │
└────────────────────────────────────────────────────────────┘
```

**Implementation:**

#### Actions Menu ([+] Icon)
**Button Behavior:** Click to open dropdown menu

```python
# In PageChat UI construction (before input field)
actions_bar = QHBoxLayout()
actions_bar.setContentsMargins(8, 4, 8, 4)
actions_bar.setSpacing(10)

# Actions dropdown button
self.btn_actions = QPushButton("+ Actions")
self.btn_actions.setFixedHeight(28)
self.btn_actions.setStyleSheet(f"""
    QPushButton {{
        background: {BG_INPUT}; 
        color: {FG_TEXT}; 
        border: 1px solid #333;
        padding: 4px 12px;
        text-align: left;
        font-size: 10px;
    }}
    QPushButton:hover {{
        border: 1px solid {ACCENT_GOLD};
    }}
""")
self.btn_actions.clicked.connect(self._show_actions_menu)

actions_bar.addWidget(self.btn_actions)
actions_bar.addStretch()

# Thinking mode button (right-aligned)
self.btn_thinking = QPushButton("⚡ Standard")
self.btn_thinking.setFixedHeight(28)
self.btn_thinking.setStyleSheet(f"""
    QPushButton {{
        background: {BG_INPUT}; 
        color: {FG_DIM}; 
        border: 1px solid #333;
        padding: 4px 12px;
        font-size: 10px;
    }}
    QPushButton:hover {{
        border: 1px solid {ACCENT_GOLD};
    }}
""")
self.btn_thinking.clicked.connect(self._show_thinking_menu)

actions_bar.addWidget(self.btn_thinking)

# Add bar to layout (above input field)
chat_layout.addLayout(actions_bar)

def _show_actions_menu(self):
    """Show actions dropdown menu"""
    menu = QMenu(self)
    menu.setStyleSheet(f"""
        QMenu {{
            background: #111; 
            color: {FG_TEXT}; 
            border: 1px solid {ACCENT_GOLD};
        }}
        QMenu::item:selected {{
            background: {ACCENT_GOLD}; 
            color: black;
        }}
    """)
    
    # File upload action
    act_upload = QAction("📎 Upload File", self)
    act_upload.triggered.connect(self._upload_file_placeholder)
    menu.addAction(act_upload)
    
    # Future actions can be added here
    # act_image = QAction("🖼️ Generate Image", self)
    # menu.addAction(act_image)
    
    # Show menu below button
    menu.exec(self.btn_actions.mapToGlobal(
        self.btn_actions.rect().bottomLeft()
    ))

def _upload_file_placeholder(self):
    """Placeholder for file upload - backend not implemented yet"""
    QMessageBox.information(
        self, 
        "File Upload",
        "File upload backend coming soon.\n\n"
        "This will allow attaching files to messages."
    )

def _show_thinking_menu(self):
    """Show thinking mode selection menu"""
    menu = QMenu(self)
    menu.setStyleSheet(f"""
        QMenu {{
            background: #111; 
            color: {FG_TEXT}; 
            border: 1px solid {ACCENT_GOLD};
        }}
        QMenu::item:selected {{
            background: {ACCENT_GOLD}; 
            color: black;
        }}
    """)
    
    # Thinking modes
    act_standard = QAction("⚡ Standard Thinking", self)
    act_standard.triggered.connect(lambda: self._set_thinking_mode("standard"))
    
    act_extended = QAction("🧠 Extended Thinking", self)
    act_extended.triggered.connect(lambda: self._set_thinking_mode("extended"))
    
    menu.addAction(act_standard)
    menu.addAction(act_extended)
    
    menu.exec(self.btn_thinking.mapToGlobal(
        self.btn_thinking.rect().bottomLeft()
    ))

def _set_thinking_mode(self, mode: str):
    """Set active thinking mode"""
    self._thinking_mode = mode
    
    if mode == "standard":
        self.btn_thinking.setText("⚡ Standard")
    elif mode == "extended":
        self.btn_thinking.setText("🧠 Extended")
    
    # Update generation parameters based on mode
    # (Backend implementation TBD)
```

**Notes:**
- Actions menu is extensible - more actions can be added later
- File upload is UI placeholder only (backend not implemented in this phase)
- Thinking mode selection updates button label but backend integration is future work

### 2.3 Date/Time Display (Terminal Only)

**Requirement:** Date/time display in top-right only visible when Terminal is active

**Current Location:** Top-right of main window (always visible)

**Change:**
```python
# In main_window.py (MonolithUI)
def _on_page_changed(self, page_id: str):
    # Show/hide date/time based on active page
    if page_id == "terminal":
        self.lbl_datetime.show()
    else:
        self.lbl_datetime.hide()
```

**Alternative:** Move date/time into Terminal addon's own header
```python
# In PageChat (Terminal addon)
# Add date/time label to chat_group header
self.lbl_datetime = QLabel()
self.lbl_datetime.setAlignment(Qt.AlignRight)
self.lbl_datetime.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")

self._datetime_timer = QTimer(self)
self._datetime_timer.timeout.connect(self._update_datetime)
self._datetime_timer.start(1000)

def _update_datetime(self):
    now = QDateTime.currentDateTime()
    self.lbl_datetime.setText(now.toString("ddd MMM dd, yyyy | hh:mm:ss"))
```

### 2.4 Operations Panel Restructuring

**Current Structure:**
```
OPERATIONS
├── [CONTROL] [ARCHIVE] (tabs)
└── Content:
    ├── Control Tab:
    │   └── ⚙ Configuration (collapsible dropdown)
    │       ├── Model Loader
    │       └── AI Configuration
    └── Archive Tab
```

**New Structure:**
```
OPERATIONS
├── [CONTROL] [ARCHIVE] [SETTINGS] (tabs)
└── Content:
    ├── Control Tab:
    │   └── Model Loader (always visible, no dropdown)
    ├── Archive Tab:
    │   └── (existing archive UI)
    └── Settings Tab:
        └── AI Configuration (moved from Configuration dropdown)
```

**Changes:**
1. Remove "Configuration" collapsible section (gear icon dropdown)
2. Keep "Model Loader" at top level in Control tab
3. Add new "SETTINGS" tab
4. Move "AI Configuration" to Settings tab

**Implementation:**

```python
# In PageChat.__init__ UI construction

# Tab buttons
tab_row = QHBoxLayout()
tab_style = f"""
    QPushButton {{
        background: #181818; border: 1px solid #333; color: {FG_DIM};
        padding: 6px 12px; font-size: 10px; font-weight: bold; border-radius: 2px;
    }}
    QPushButton:checked {{
        background: #222; color: {ACCENT_GOLD}; border: 1px solid {ACCENT_GOLD};
    }}
    QPushButton:hover {{ color: {FG_TEXT}; border: 1px solid {FG_TEXT}; }}
"""

self.btn_tab_control = SkeetButton("CONTROL")
self.btn_tab_control.setCheckable(True)
self.btn_tab_control.setChecked(True)
self.btn_tab_control.setStyleSheet(tab_style)

self.btn_tab_archive = SkeetButton("ARCHIVE")
self.btn_tab_archive.setCheckable(True)
self.btn_tab_archive.setStyleSheet(tab_style)

self.btn_tab_settings = SkeetButton("SETTINGS")  # NEW TAB
self.btn_tab_settings.setCheckable(True)
self.btn_tab_settings.setStyleSheet(tab_style)

tab_group = QButtonGroup(self)
tab_group.setExclusive(True)
tab_group.addButton(self.btn_tab_control)
tab_group.addButton(self.btn_tab_archive)
tab_group.addButton(self.btn_tab_settings)  # NEW

tab_row.addWidget(self.btn_tab_control)
tab_row.addWidget(self.btn_tab_archive)
tab_row.addWidget(self.btn_tab_settings)  # NEW
tab_row.addStretch()

operations_layout.addLayout(tab_row)

# Stacked widget for tab content
self.ops_stack = QStackedWidget()

# === CONTROL TAB ===
control_tab = QWidget()
control_layout = QVBoxLayout(control_tab)
control_layout.setSpacing(12)

# Model Loader (always visible, no collapsible wrapper)
grp_load = SkeetGroupBox("MODEL LOADER")
self.path_display = QLineEdit()
self.path_display.setReadOnly(True)
self.path_display.setPlaceholderText("No GGUF Selected")
self.path_display.setStyleSheet(
    f"background: {BG_INPUT}; color: #555; border: 1px solid #333; padding: 5px;"
)
btn_browse = SkeetButton("...")
btn_browse.setFixedWidth(30)
btn_browse.clicked.connect(self.pick_file)

row_file = QHBoxLayout()
row_file.addWidget(self.path_display)
row_file.addWidget(btn_browse)

self.btn_load = SkeetButton("LOAD MODEL")
self.btn_load.clicked.connect(self.toggle_load)

grp_load.add_layout(row_file)
grp_load.add_widget(self.btn_load)

control_layout.addWidget(grp_load)
control_layout.addStretch()

# === ARCHIVE TAB ===
archive_tab = QWidget()
archive_layout = QVBoxLayout(archive_tab)
archive_layout.setSpacing(10)

# Archive controls
archive_controls = QHBoxLayout()
self.btn_save_chat = SkeetButton("SAVE")
self.btn_save_chat.clicked.connect(self._save_chat_archive)
self.btn_load_chat = SkeetButton("LOAD")
self.btn_load_chat.clicked.connect(self._load_chat_archive)
self.btn_delete_chat = SkeetButton("DELETE")
self.btn_delete_chat.clicked.connect(self._delete_selected_archive)
self.btn_clear_chat = SkeetButton("CLEAR")
self.btn_clear_chat.clicked.connect(lambda: self._clear_current_session(delete_archive=False))

archive_controls.addWidget(self.btn_save_chat)
archive_controls.addWidget(self.btn_load_chat)
archive_controls.addWidget(self.btn_delete_chat)
archive_controls.addWidget(self.btn_clear_chat)
archive_controls.addStretch()

archive_layout.addLayout(archive_controls)

# Archive list
self.archive_list = QListWidget()
self.archive_list.setStyleSheet(f"""
    QListWidget {{
        background: {BG_INPUT}; color: {FG_TEXT}; border: 1px solid #222;
        font-family: 'Consolas', monospace; font-size: 10px;
    }}
    QListWidget::item {{ padding: 6px; }}
    QListWidget::item:selected {{ background: #222; color: {ACCENT_GOLD}; }}
    {SCROLLBAR_STYLE}
""")
archive_layout.addWidget(self.archive_list)

# === SETTINGS TAB (NEW) ===
settings_tab = QWidget()
settings_layout = QVBoxLayout(settings_tab)
settings_layout.setSpacing(12)

# AI Configuration (moved from Configuration dropdown)
grp_ai = SkeetGroupBox("AI CONFIGURATION")

self.s_temp = SkeetSlider("Temperature", 0.1, 2.0, self.config.get("temp", 0.7))
self.s_temp.valueChanged.connect(lambda v: self._update_config_value("temp", v))

self.s_top = SkeetSlider("Top-P", 0.1, 1.0, self.config.get("top_p", 0.9))
self.s_top.valueChanged.connect(lambda v: self._update_config_value("top_p", v))

self.s_tok = SkeetSlider(
    "Max Tokens", 512, 8192, self.config.get("max_tokens", 2048), is_int=True
)
self.s_tok.valueChanged.connect(
    lambda v: self._update_config_value("max_tokens", int(v))
)

self.s_ctx = SkeetSlider(
    "Context Limit", 1024, 16384, self.config.get("ctx_limit", 8192), is_int=True
)
self.s_ctx.valueChanged.connect(self._on_ctx_limit_changed)

lbl_sys = QLabel("Behavior Tags")
lbl_sys.setStyleSheet(f"color: {FG_DIM}; font-size: 11px; margin-top: 5px;")

self.behavior_tags = BehaviorTagInput([])
self.behavior_tags.tagsChanged.connect(self._on_behavior_tags_changed)

# Save/Reset buttons (from Config System Overhaul)
config_actions = QHBoxLayout()
btn_save_config = SkeetButton("SAVE CONFIG")
btn_save_config.clicked.connect(self._save_config)
btn_reset_config = SkeetButton("RESET TO DEFAULT")
btn_reset_config.clicked.connect(self._reset_config)
config_actions.addWidget(btn_save_config)
config_actions.addWidget(btn_reset_config)
config_actions.addStretch()

grp_ai.add_widget(self.s_temp)
grp_ai.add_widget(self.s_top)
grp_ai.add_widget(self.s_tok)
grp_ai.add_widget(self.s_ctx)
grp_ai.add_widget(lbl_sys)
grp_ai.add_widget(self.behavior_tags)
grp_ai.add_layout(config_actions)

settings_layout.addWidget(grp_ai)
settings_layout.addStretch()

# Add all tabs to stack
self.ops_stack.addWidget(control_tab)    # Index 0
self.ops_stack.addWidget(archive_tab)    # Index 1
self.ops_stack.addWidget(settings_tab)   # Index 2

# Connect tab switches
self.btn_tab_control.toggled.connect(lambda checked: self._switch_ops_tab(0, checked))
self.btn_tab_archive.toggled.connect(lambda checked: self._switch_ops_tab(1, checked))
self.btn_tab_settings.toggled.connect(lambda checked: self._switch_ops_tab(2, checked))

operations_group.add_layout(operations_layout)
```

**Benefits:**
- Model Loader always accessible (no need to expand dropdown)
- Settings separated from operational controls
- Cleaner visual hierarchy
- Consistent with other addon UIs

---

## 3. MESSAGE ACTIONS SYSTEM

### 3.1 Scope and Constraints

**Allowed Actions:**
- **Last message pair only** (last user message + last assistant response)
- Cannot edit/delete/regen messages older than last interaction
- Jenga piece logic: Deleting a message deletes all subsequent messages

**Rationale:** 
- Prevents conversation corruption from editing middle messages
- Avoids complex state management of conversation tree branches
- Maintains linear conversation integrity

### 3.2 Message Actions UI

**Actions Per Message:**
- **User message (last only):** [Edit] [Delete]
- **Assistant message (last only):** [Edit] [Delete] [Regen]

**UI Pattern:** Hover-reveal icons

```python
# In PageChat
class MessageWidget(QWidget):
    """Individual message container with hover actions"""
    sig_edit = Signal(int)    # message_index
    sig_delete = Signal(int)
    sig_regen = Signal(int)   # assistant messages only
    
    def __init__(self, message_index: int, role: str, text: str):
        super().__init__()
        self.message_index = message_index
        self.role = role
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        
        # Message content
        self.lbl_content = QLabel(text)
        layout.addWidget(self.lbl_content, 1)
        
        # Action buttons (hidden by default)
        self.action_panel = QWidget()
        action_layout = QHBoxLayout(self.action_panel)
        action_layout.setSpacing(4)
        
        self.btn_edit = QPushButton("✎")
        self.btn_edit.setFixedSize(20, 20)
        self.btn_edit.clicked.connect(lambda: self.sig_edit.emit(self.message_index))
        
        self.btn_delete = QPushButton("×")
        self.btn_delete.setFixedSize(20, 20)
        self.btn_delete.clicked.connect(lambda: self.sig_delete.emit(self.message_index))
        
        action_layout.addWidget(self.btn_edit)
        action_layout.addWidget(self.btn_delete)
        
        if role == "assistant":
            self.btn_regen = QPushButton("⟳")
            self.btn_regen.setFixedSize(20, 20)
            self.btn_regen.clicked.connect(lambda: self.sig_regen.emit(self.message_index))
            action_layout.addWidget(self.btn_regen)
        
        self.action_panel.hide()
        layout.addWidget(self.action_panel)
    
    def enterEvent(self, event):
        self.action_panel.show()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self.action_panel.hide()
        super().leaveEvent(event)
```

### 3.3 Message Index Tracking

**Current System:** Terminal uses `QTextEdit` with HTML appending

**Challenge:** QTextEdit doesn't have built-in message indexing

**Issue with Current Approach:** Messages rendered as HTML have visual inconsistency (gray text → white on UPDATE), no structured access to individual messages, difficult to attach interactive elements

**Solution Options:**

#### Option A: Migrate to QListWidget with MessageWidget items (RECOMMENDED)
**Why:** Structure. Each message becomes a real object you can attach buttons to, not HTML text you have to parse positions for. Clean hover states, proper message boundaries, easy action button integration.

```python
# Replace self.chat (QTextEdit) with message list
self.message_list = QListWidget()
self.messages = []  # list[dict] with role, content, index

def append_user_message(self, text: str):
    msg_data = {"role": "user", "content": text, "index": len(self.messages)}
    self.messages.append(msg_data)
    
    widget = MessageWidget(msg_data["index"], "user", text)
    widget.sig_edit.connect(self._on_edit_message)
    widget.sig_delete.connect(self._on_delete_message)
    
    # Only show actions for last message
    if msg_data["index"] == len(self.messages) - 1:
        widget.actions_enabled = True
    
    item = QListWidgetItem(self.message_list)
    item.setSizeHint(widget.sizeHint())
    self.message_list.addItem(item)
    self.message_list.setItemWidget(item, widget)
```

#### Option B: Keep QTextEdit, add message tracking layer
```python
# Maintain parallel message index structure
self.message_boundaries = []  # list[dict] with start_pos, end_pos, role, index

def append_user_message(self, text: str):
    start_pos = self.chat.textCursor().position()
    
    # Append HTML as before
    self.chat.append(f"<b>USER:</b> {html.escape(text)}")
    
    end_pos = self.chat.textCursor().position()
    
    self.message_boundaries.append({
        "role": "user",
        "content": text,
        "start_pos": start_pos,
        "end_pos": end_pos,
        "index": len(self.message_boundaries)
    })
    
    # Add action buttons only for last message
    if self._is_last_message_pair():
        self._insert_action_buttons(len(self.message_boundaries) - 1)
```

**Recommendation:** Option A (QListWidget) for cleaner action button management

### 3.4 Edit Action

**User Message Edit:**
```python
def _on_edit_message(self, message_index: int):
    msg = self.messages[message_index]
    
    # Show inline editor
    dialog = QInputDialog(self)
    dialog.setWindowTitle("Edit Message")
    dialog.setLabelText("Edit your message:")
    dialog.setTextValue(msg["content"])
    dialog.resize(500, 200)
    
    if dialog.exec() == QDialog.Accepted:
        new_text = dialog.textValue()
        
        # Update message content
        msg["content"] = new_text
        
        # Delete assistant response (cascade)
        self._delete_message_cascade(message_index + 1)
        
        # Auto-regen with new prompt
        self._regenerate_from_message(message_index)
```

**Assistant Message Edit:**
```python
def _on_edit_assistant_message(self, message_index: int):
    msg = self.messages[message_index]
    
    # Show multi-line text editor
    dialog = QDialog(self)
    dialog.setWindowTitle("Edit Response")
    layout = QVBoxLayout(dialog)
    
    text_edit = QTextEdit()
    text_edit.setPlainText(msg["content"])
    layout.addWidget(text_edit)
    
    btn_box = QHBoxLayout()
    btn_save = QPushButton("Save")
    btn_cancel = QPushButton("Cancel")
    btn_box.addWidget(btn_save)
    btn_box.addWidget(btn_cancel)
    layout.addLayout(btn_box)
    
    btn_save.clicked.connect(dialog.accept)
    btn_cancel.clicked.connect(dialog.reject)
    
    if dialog.exec() == QDialog.Accepted:
        new_text = text_edit.toPlainText()
        msg["content"] = new_text
        
        # Update conversation history for LLM
        self._update_llm_conversation_history()
        
        # Refresh display
        self._refresh_message_display()
```

### 3.5 Delete Action (Jenga Piece Logic)

**Cascade Deletion:**
```python
def _on_delete_message(self, message_index: int):
    msg = self.messages[message_index]
    
    # Confirm deletion
    reply = QMessageBox.question(
        self, 
        "Delete Message",
        f"Delete this {msg['role']} message?\n\n"
        "This will also delete all subsequent messages.",
        QMessageBox.Yes | QMessageBox.No
    )
    
    if reply == QMessageBox.Yes:
        self._delete_message_cascade(message_index)

def _delete_message_cascade(self, start_index: int):
    """Delete message and all following messages"""
    # Must wait for any active generation to complete
    if self._is_running:
        self.sig_stop.emit()
        # Wait for READY state
        QTimer.singleShot(100, lambda: self._delete_message_cascade(start_index))
        return
    
    # Remove messages from index onwards
    del self.messages[start_index:]
    
    # Update LLM conversation history
    self._update_llm_conversation_history()
    
    # Refresh display
    self._refresh_message_display()
```

**Pair Deletion:**
```python
def _delete_pair(self, user_message_index: int):
    """Delete user message and associated assistant response"""
    assistant_index = user_message_index + 1
    
    if assistant_index < len(self.messages):
        # Delete both
        del self.messages[user_message_index:assistant_index+1]
    else:
        # Only user message exists
        del self.messages[user_message_index]
    
    self._update_llm_conversation_history()
    self._refresh_message_display()
```

### 3.6 Regen Action

**Objective:** Resubmit last user prompt using UPDATE mechanism

**Current UPDATE Mechanism:**
```python
# In LLMEngine.generate()
if command == "update":
    # Removes last assistant message from conversation_history
    # Regenerates response with existing user prompt
```

**Regen Implementation:**
```python
def _on_regen_message(self, message_index: int):
    """Regenerate assistant response for last message pair"""
    if message_index != len(self.messages) - 1:
        return  # Only allow regen on last message
    
    # Remove current assistant response
    del self.messages[message_index]
    
    # Get previous user message
    user_index = message_index - 1
    user_msg = self.messages[user_index]
    
    # Trigger UPDATE generation
    self._set_send_button_state(is_running=True)
    
    # Submit UPDATE task
    self.sig_update.emit(user_msg["content"])  # New signal

# In builtin.py wiring
w.sig_update.connect(
    lambda prompt: ctx.bridge.submit(
        ctx.bridge.wrap(
            "terminal", "update", "llm",
            payload={"prompt": prompt, "config": w.config}
        )
    )
)
```

### 3.7 Undo/Redo System

**Objective:** Allow reverting input field text changes (NOT full message history)

**Scope:** Terminal input field only - standard text editing undo/redo

**Implementation Strategy:** Qt's built-in QLineEdit undo/redo

```python
# In PageChat.__init__
# QLineEdit has built-in undo/redo support
self.input = QLineEdit()
self.input.setUndoRedoEnabled(True)  # Enabled by default

# Optional: Add explicit keyboard shortcuts for visibility
QShortcut(QKeySequence("Ctrl+Z"), self.input, activated=self.input.undo)
QShortcut(QKeySequence("Ctrl+Y"), self.input, activated=self.input.redo)
```

**Note:** This does NOT implement undo/redo for message edits/deletes. Those operations are immediate and permanent (with cascade deletion). If full message history undo is needed later, implement the command pattern described below.

<details>
<summary>Optional: Full Message History Undo/Redo (Future Enhancement)</summary>

If you want to undo message edits/deletes, use command pattern:

```python
class MessageCommand:
    """Base class for reversible message operations"""
    def execute(self): pass
    def undo(self): pass

class DeleteMessageCommand(MessageCommand):
    def __init__(self, messages: list, index: int):
        self.messages = messages
        self.index = index
        self.deleted_messages = []
    
    def execute(self):
        self.deleted_messages = self.messages[self.index:]
        del self.messages[self.index:]
    
    def undo(self):
        self.messages.extend(self.deleted_messages)

class EditMessageCommand(MessageCommand):
    def __init__(self, message: dict, new_content: str):
        self.message = message
        self.old_content = message["content"]
        self.new_content = new_content
    
    def execute(self):
        self.message["content"] = self.new_content
    
    def undo(self):
        self.message["content"] = self.old_content

# In PageChat
self._command_history = []  # Stack of MessageCommand
self._command_position = 0

def _execute_command(self, command: MessageCommand):
    command.execute()
    self._command_history = self._command_history[:self._command_position]
    self._command_history.append(command)
    self._command_position += 1
    self._refresh_message_display()

def _undo(self):
    if self._command_position > 0:
        self._command_position -= 1
        cmd = self._command_history[self._command_position]
        cmd.undo()
        self._refresh_message_display()

def _redo(self):
    if self._command_position < len(self._command_history):
        cmd = self._command_history[self._command_position]
        cmd.execute()
        self._command_position += 1
        self._refresh_message_display()

# Keyboard shortcuts
QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._undo)
QShortcut(QKeySequence("Ctrl+Y"), self, activated=self._redo)
```

**UI Buttons:**
```python
# Add to chat controls
btn_undo = SkeetButton("⎌ UNDO")
btn_undo.setFixedWidth(60)
btn_undo.clicked.connect(self._undo)

btn_redo = SkeetButton("⟳ REDO")
btn_redo.setFixedWidth(60)
btn_redo.clicked.connect(self._redo)

chat_controls.addWidget(btn_undo)
chat_controls.addWidget(btn_redo)
```

</details>

---

## 4. BUG FIXES

### 4.1 QTextEdit Stylesheet Parsing Error

**Error Message:**
```
Could not parse stylesheet of object QTextEdit(0x1d9957f49f0)
```

**When It Occurs:** Only when opening Terminal addon

**Action:** Do NOT fix yet - preserve for Overseer debugging

**Implementation:**
```python
# In Overseer, add error capture
# This error should appear in viztracer logs as [ERROR]
# Used as test case for Overseer functionality
```

### 4.2 Trace Severity Labeling

**Current Code (Incorrect):**
```python
elif "error" in lowered:
    state = "COMPLETE"  # ← WRONG
```

**Fixed Code:**
```python
elif "error" in lowered:
    state = "ERROR"  # ← CORRECT
```

**Location:** Find in trace message processing logic (likely in `PageChat.append_trace()`)

**Implementation:**
```python
def append_trace(self, message: str):
    lowered = message.lower()
    
    # Determine severity
    if "error" in lowered or "fail" in lowered:
        state = "ERROR"
        color = FG_ERROR
    elif "warn" in lowered:
        state = "WARNING"
        color = FG_WARN
    elif "complete" in lowered or "success" in lowered:
        state = "COMPLETE"
        color = FG_ACCENT
    else:
        state = "INFO"
        color = FG_DIM
    
    # Format with severity tag
    formatted = f"<span style='color:{color}'>[{state}]</span> {message}"
    self.trace_log.append(formatted)
```

### 4.3 _topic_dominant Heuristic

**Current Implementation:** Requires 3+ repeated 4-letter words

**Issue:** Too strict, fails to detect topics in normal conversation

**Suggested Relaxation:**
```python
def _topic_dominant(self, text: str) -> bool:
    """Detect if text contains dominant topic keywords"""
    words = text.lower().split()
    word_freq = {}
    
    for word in words:
        if len(word) >= 4:  # Still 4-letter minimum
            word_freq[word] = word_freq.get(word, 0) + 1
    
    # Relaxed threshold: 2+ occurrences instead of 3+
    dominant_words = [w for w, count in word_freq.items() if count >= 2]
    
    return len(dominant_words) > 0
```

### 4.4 Config Path Consolidation

**Current Mess:**
```
C:\Models\llama_env\ui\addons\configs\llm_config.json
C:\Models\llama_env\config\vision_config.json
C:\Models\llama_env\config\audiogen_config.json
```

**Issue:** Configs scattered across multiple locations, inconsistent paths

**Unified Structure:**
```
C:\Monolith\
├── config\
│   ├── addons\
│   │   ├── llm.json
│   │   ├── vision.json
│   │   └── audio.json
│   ├── operators\
│   │   └── *.json
│   └── logs\
│       ├── overseer.db        # SQLite for Overseer logs
│       └── trace_*.json       # Viztracer session dumps
├── models\                    # Optional: User can point here
└── outputs\                   # Generated content
    ├── images\
    └── audio\
```

**Implementation Changes:**

**In `core/llm_config.py`:**
```python
CONFIG_PATH = Path("C:/Monolith/config/addons/llm.json")
```

**In Vision module (`ui/modules/sd.py`):**
```python
self.config_path = Path("C:/Monolith/config/addons/vision.json")
self.legacy_config_path = Path("C:/Models/llama_env/config/vision_config.json")  # Migration
```

**In Audio module:**
```python
self.config_path = Path("C:/Monolith/config/addons/audio.json")
```

**Bootstrap initialization:**
```python
# In bootstrap.py - Create Monolith directory structure
MONOLITH_ROOT = Path("C:/Monolith")
MONOLITH_ROOT.mkdir(parents=True, exist_ok=True)
(MONOLITH_ROOT / "config/addons").mkdir(parents=True, exist_ok=True)
(MONOLITH_ROOT / "config/operators").mkdir(parents=True, exist_ok=True)
(MONOLITH_ROOT / "config/logs").mkdir(parents=True, exist_ok=True)
(MONOLITH_ROOT / "outputs/images").mkdir(parents=True, exist_ok=True)
(MONOLITH_ROOT / "outputs/audio").mkdir(parents=True, exist_ok=True)
```

**Migration Strategy:**
```python
# In each module's _load_config()
def _load_config(self):
    if self.config_path.exists():
        # New path exists, use it
        return self._read_config(self.config_path)
    elif hasattr(self, 'legacy_config_path') and self.legacy_config_path.exists():
        # Migrate from old location
        config = self._read_config(self.legacy_config_path)
        self._save_config(config)  # Save to new location
        return config
    else:
        # First run, use defaults
        return self._get_default_config()
```

---

## 5. TOPIC GENERATION

### 5.1 Two-Phase Topic Naming

**Phase 1: Initial Summary (200-300 tokens)**
- Triggered after first user-assistant exchange reaches 200-300 tokens
- LLM generates short title (constraint: max 50 characters)
- Title replaces "Untitled Chat" in Archive list

**Phase 2: Refined Title (Crystallized Thought)**
- Triggered after conversation develops substantial content
- LLM summarizes entire conversation into concise title
- Updates Archive entry

### 5.2 Implementation Architecture

**Token Counter:**
```python
# In PageChat
self._session_token_count = 0
self._title_phase = 0  # 0=untitled, 1=initial, 2=refined

def append_token(self, token: str):
    self._token_buf.append(token)
    self._session_token_count += 1
    
    # Check for title generation triggers
    if self._title_phase == 0 and self._session_token_count >= 250:
        self._generate_initial_title()
    elif self._title_phase == 1 and self._session_token_count >= 1500:
        self._generate_refined_title()
```

**Title Generation Task:**
```python
def _generate_initial_title(self):
    """Phase 1: Generate short summary after first exchange"""
    if self._title_generated:
        return
    
    # Construct prompt for title generation
    conversation_text = self._get_conversation_text()
    
    prompt = f"""Based on this conversation, generate a short title (max 50 characters):

{conversation_text}

Reply with ONLY the title, no explanation or quotes."""
    
    # Submit background task (priority 3)
    task = self.ctx.bridge.wrap(
        "terminal_title_gen",
        "generate",
        "llm",
        payload={
            "prompt": prompt,
            "config": {
                "temp": 0.3,  # Low temp for consistency
                "max_tokens": 20,
                "ctx_limit": 2048,
            }
        }
    )
    task.priority = 3  # Background priority
    self.ctx.bridge.submit(task)
    
    # Connect to separate handler
    self.ctx.guard.sig_token.connect(self._on_title_token)

def _on_title_token(self, token: str):
    """Accumulate title generation tokens"""
    if not hasattr(self, '_title_buffer'):
        self._title_buffer = []
    
    self._title_buffer.append(token)

def _on_title_complete(self):
    """Finalize generated title"""
    title = ''.join(self._title_buffer).strip()
    
    # Truncate if too long
    if len(title) > 50:
        title = title[:47] + "..."
    
    # Update session title
    self._current_session["title"] = title
    self._title_phase = 1
    self._title_generated = True
    
    # Refresh archive list to show new title
    self._refresh_archive_list()
    
    del self._title_buffer
```

**Refined Title (Phase 2):**
```python
def _generate_refined_title(self):
    """Phase 2: Update title based on developed conversation"""
    conversation_text = self._get_conversation_text()
    
    prompt = f"""This conversation has developed significantly. 
Summarize its main topic in a concise title (max 50 characters):

{conversation_text}

Reply with ONLY the title."""
    
    # Same background task pattern as Phase 1
    # ...
```

### 5.3 Archive Integration

**Current Archive Format:**
```json
{
  "id": "chat_1738734127_0001",
  "title": "Untitled Chat",
  "messages": [...],
  "timestamp": 1738734127.5,
  "token_count": 0
}
```

**Updated Format:**
```json
{
  "id": "chat_1738734127_0001",
  "title": "Config System Architecture",  // Auto-generated
  "title_phase": 2,                      // 0/1/2
  "messages": [...],
  "timestamp": 1738734127.5,
  "token_count": 1847
}
```

**Archive List Display:**
```python
def _refresh_archive_list(self):
    self.archive_list.clear()
    
    for path in sorted(self._archive_dir.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                session = json.load(f)
            
            title = session.get("title", "Untitled Chat")
            timestamp = session.get("timestamp", 0)
            token_count = session.get("token_count", 0)
            phase = session.get("title_phase", 0)
            
            # Format with phase indicator
            phase_icon = ["❓", "📝", "✓"][phase]
            display_text = f"{phase_icon} {title} ({token_count} tokens)"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, str(path))
            self.archive_list.addItem(item)
        except Exception:
            pass
```

---

## 6. OPERATOR SYSTEM + HUB LANDING PAGE

### 6.1 System Architecture

**Objective:** Save and restore complete workspace configurations

**Operator Definition:**
- Collection of loaded addons with their configurations
- Window geometry and splitter positions
- UI state (which tabs/sections are expanded)
- NO model loading (too resource-intensive)

**Config Hierarchy:**
```
DEFAULT_CONFIG (code)
    ↓
Operator Config (saved preset)
    ↓
Session Config (active, in-memory)
    ↓
Disk Config (on user Save)
```

### 6.2 HUB Addon Specification

**Addon Type:** Page addon (full-screen)  
**ID:** `hub`  
**Always Loaded:** Yes (system addon)  
**Kernel Contract Compliance:** Full (via AddonContext)

**AddonSpec Registration:**
```python
# In ui/addons/builtin.py

def hub_factory(ctx: AddonContext) -> QWidget:
    w = PageHub(ctx.state)
    
    # OUTGOING (hub → kernel)
    w.sig_load_operator.connect(
        lambda operator_name: ctx.bridge.submit(
            ctx.bridge.wrap("hub", "load_operator", "system",
                          payload={"operator": operator_name})
        )
    )
    
    # INCOMING (kernel → hub)
    # Hub mostly operates on local state, minimal kernel interaction
    
    return w

# Register as system page
registry.register(AddonSpec(
    id="hub",
    kind="page",
    title="HUB",
    icon="⌂",
    factory=hub_factory
))
```

### 6.3 Operator File Structure

**Directory:** `C:/Monolith/config/operators/`

**Storage:** JSON files (human-readable, easy backup, version control friendly)

**File Format:** `{operator_name}.json`

**Schema:**
```json
{
  "version": 1,
  "name": "Development Setup",
  "created": 1738734127.5,
  "modified": 1738734200.3,
  "addons": {
    "terminal": {
      "enabled": true,
      "config": {
        "gguf_path": "C:/Models/qwen.gguf",
        "temp": 0.7,
        "top_p": 0.9,
        "max_tokens": 4096,
        "ctx_limit": 16384,
        "behavior_tags": ["helpful", "concise"]
      },
      "window_state": {
        "splitter_sizes": [800, 400]
      }
    },
    "vision": {
      "enabled": true,
      "config": {
        "model_path": "C:/Models/sd_v1-5.safetensors",
        "steps": 30,
        "guidance": 7.5
      }
    },
    "audio": {
      "enabled": false
    }
  },
  "ui_state": {
    "main_splitter": [1200, 300],
    "window_geometry": [100, 100, 1600, 900]
  }
}
```

### 6.4 HUB Page UI

**Layout:**
```
┌─────────────────────────────────────────────┐
│              MONOLITH HUB                   │
├─────────────────────────────────────────────┤
│                                             │
│   ┌───────────────────────────────────┐    │
│   │  WORKSPACE OPERATORS              │    │
│   ├───────────────────────────────────┤    │
│   │  [+] New  [-] Delete  [✎] Edit    │    │
│   ├───────────────────────────────────┤    │
│   │                                   │    │
│   │  Development Setup                │    │
│   │  Research Configuration           │    │
│   │  Content Creation                 │    │
│   │  → Default Workspace (active)     │    │
│   │                                   │    │
│   └───────────────────────────────────┘    │
│                                             │
│   [⚙ Set as Startup Operator]              │
│   [▶ Load Selected]                        │
│                                             │
│   ┌───────────────────────────────────┐    │
│   │  SYSTEM STATUS                    │    │
│   │  Vitals: CPU 12% | RAM 4.2GB      │    │
│   │  Status: READY                    │    │
│   └───────────────────────────────────┘    │
│                                             │
└─────────────────────────────────────────────┘
```

**Implementation:**
```python
class PageHub(QWidget):
    sig_load_operator = Signal(str)
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.operators_dir = Path("config/operators")
        self.operators_dir.mkdir(parents=True, exist_ok=True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # Title
        title = QLabel("MONOLITH HUB")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"""
            font-size: 24px; 
            font-weight: bold; 
            color: {ACCENT_GOLD};
            margin-bottom: 20px;
        """)
        layout.addWidget(title)
        
        # Operators group
        grp_operators = SkeetGroupBox("WORKSPACE OPERATORS")
        op_layout = QVBoxLayout()
        
        # Toolbar
        toolbar = QHBoxLayout()
        btn_new = SkeetButton("+ NEW")
        btn_new.clicked.connect(self._create_operator)
        btn_delete = SkeetButton("- DELETE")
        btn_delete.clicked.connect(self._delete_operator)
        btn_edit = SkeetButton("✎ EDIT")
        btn_edit.clicked.connect(self._edit_operator)
        
        toolbar.addWidget(btn_new)
        toolbar.addWidget(btn_delete)
        toolbar.addWidget(btn_edit)
        toolbar.addStretch()
        op_layout.addLayout(toolbar)
        
        # Operators list
        self.operator_list = QListWidget()
        self.operator_list.setStyleSheet(f"""
            QListWidget {{
                background: {BG_INPUT}; 
                color: {FG_TEXT}; 
                border: 1px solid #222;
                font-size: 12px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid #1a1a1a;
            }}
            QListWidget::item:selected {{
                background: #222; 
                color: {ACCENT_GOLD};
            }}
        """)
        op_layout.addWidget(self.operator_list)
        
        # Actions
        actions = QHBoxLayout()
        self.chk_startup = QCheckBox("Set as Startup Operator")
        self.chk_startup.setStyleSheet(f"color: {FG_DIM};")
        self.chk_startup.stateChanged.connect(self._set_startup_operator)
        
        self.btn_load = SkeetButton("▶ LOAD SELECTED")
        self.btn_load.clicked.connect(self._load_selected_operator)
        
        actions.addWidget(self.chk_startup)
        actions.addStretch()
        actions.addWidget(self.btn_load)
        op_layout.addLayout(actions)
        
        grp_operators.add_layout(op_layout)
        layout.addWidget(grp_operators)
        
        # System status (moved from top-left)
        grp_status = SkeetGroupBox("SYSTEM STATUS")
        status_layout = QVBoxLayout()
        
        self.lbl_vitals = QLabel()
        self.lbl_vitals.setStyleSheet(f"color: {FG_TEXT}; font-size: 11px;")
        
        self.lbl_kernel_status = QLabel()
        self.lbl_kernel_status.setStyleSheet(f"color: {FG_ACCENT}; font-size: 11px;")
        
        status_layout.addWidget(self.lbl_vitals)
        status_layout.addWidget(self.lbl_kernel_status)
        
        grp_status.add_layout(status_layout)
        layout.addWidget(grp_status)
        
        layout.addStretch()
        
        # Load operators
        self._refresh_operator_list()
        
        # Start vitals timer
        self._vitals_timer = QTimer(self)
        self._vitals_timer.timeout.connect(self._update_vitals)
        self._vitals_timer.start(2000)
```

### 6.5 Operator Manager

**Singleton Service:** Manages operator CRUD operations

```python
# core/operator_manager.py

from dataclasses import dataclass, asdict
from pathlib import Path
import json
from typing import Dict, Any

@dataclass
class OperatorConfig:
    version: int = 1
    name: str = ""
    created: float = 0.0
    modified: float = 0.0
    addons: Dict[str, Any] = None
    ui_state: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.addons is None:
            self.addons = {}
        if self.ui_state is None:
            self.ui_state = {}

class OperatorManager:
    """Manages workspace operator presets"""
    
    def __init__(self, operators_dir: Path):
        self.operators_dir = operators_dir
        self.operators_dir.mkdir(parents=True, exist_ok=True)
        self.startup_operator_file = operators_dir / "_startup.txt"
    
    def list_operators(self) -> list[str]:
        """Return list of operator names"""
        return [p.stem for p in self.operators_dir.glob("*.json")]
    
    def load_operator(self, name: str) -> OperatorConfig | None:
        """Load operator from disk"""
        path = self.operators_dir / f"{name}.json"
        if not path.exists():
            return None
        
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return OperatorConfig(**data)
        except Exception as e:
            print(f"Error loading operator {name}: {e}")
            return None
    
    def save_operator(self, config: OperatorConfig) -> bool:
        """Save operator to disk"""
        path = self.operators_dir / f"{config.name}.json"
        
        try:
            config.modified = time.time()
            with path.open("w", encoding="utf-8") as f:
                json.dump(asdict(config), f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving operator {config.name}: {e}")
            return False
    
    def delete_operator(self, name: str) -> bool:
        """Delete operator file"""
        path = self.operators_dir / f"{name}.json"
        try:
            path.unlink()
            return True
        except Exception:
            return False
    
    def get_startup_operator(self) -> str | None:
        """Get name of operator to load on startup"""
        if self.startup_operator_file.exists():
            return self.startup_operator_file.read_text().strip()
        return None
    
    def set_startup_operator(self, name: str | None):
        """Set operator to load on startup"""
        if name:
            self.startup_operator_file.write_text(name)
        else:
            self.startup_operator_file.unlink(missing_ok=True)
    
    def capture_current_state(self, ui: 'MonolithUI') -> OperatorConfig:
        """Capture current Monolith state into operator config"""
        config = OperatorConfig()
        config.created = time.time()
        config.modified = config.created
        
        # Capture addon states
        for addon_id, instance in ui.host._instances.items():
            addon_config = {}
            
            # Get addon-specific config
            if hasattr(instance, 'config'):
                addon_config['config'] = instance.config.copy()
            
            # Get window state (splitters, etc.)
            if hasattr(instance, 'saveGeometry'):
                # addon_config['geometry'] = instance.saveGeometry()
                pass
            
            config.addons[addon_id] = addon_config
        
        # Capture UI state
        config.ui_state = {
            'window_geometry': [
                ui.x(), ui.y(), ui.width(), ui.height()
            ],
            'main_splitter': ui.main_splitter.sizes() if hasattr(ui, 'main_splitter') else []
        }
        
        return config
    
    def apply_operator(self, config: OperatorConfig, ui: 'MonolithUI'):
        """Apply operator config to current Monolith state"""
        # Apply addon configs
        for addon_id, addon_data in config.addons.items():
            if not addon_data.get('enabled', True):
                continue
            
            # Launch addon if not already loaded
            instance = ui.host.get_instance(addon_id)
            if not instance:
                instance = ui.host.launch_module(addon_id)
            
            # Apply config
            if 'config' in addon_data and hasattr(instance, 'config'):
                instance.config.update(addon_data['config'])
                # Trigger config reload in addon
                if hasattr(instance, '_update_ui_from_config'):
                    instance._update_ui_from_config()
        
        # Apply UI state
        if 'window_geometry' in config.ui_state:
            geom = config.ui_state['window_geometry']
            ui.setGeometry(geom[0], geom[1], geom[2], geom[3])
        
        if 'main_splitter' in config.ui_state and hasattr(ui, 'main_splitter'):
            ui.main_splitter.setSizes(config.ui_state['main_splitter'])
```

### 6.6 Operator Lifecycle

**Create New Operator:**
```python
def _create_operator(self):
    name, ok = QInputDialog.getText(
        self, "New Operator", "Operator Name:"
    )
    
    if ok and name:
        # Capture current state
        config = self.operator_manager.capture_current_state(self.ui)
        config.name = name
        
        # Save
        if self.operator_manager.save_operator(config):
            self._refresh_operator_list()
```

**Load Operator:**
```python
def _load_selected_operator(self):
    selected = self.operator_list.currentItem()
    if not selected:
        return
    
    operator_name = selected.text()
    config = self.operator_manager.load_operator(operator_name)
    
    if config:
        # Apply to current UI
        self.operator_manager.apply_operator(config, self.ui)
        
        # Switch to appropriate page
        self.ui.switch_page("terminal")  # or first enabled addon
```

**Save Current State to Operator:**
```python
def _save_current_to_operator(self):
    selected = self.operator_list.currentItem()
    if not selected:
        return
    
    operator_name = selected.text()
    config = self.operator_manager.load_operator(operator_name)
    
    if config:
        # Update with current state
        updated = self.operator_manager.capture_current_state(self.ui)
        updated.name = config.name
        updated.created = config.created
        
        self.operator_manager.save_operator(updated)
```

### 6.7 Bootstrap Integration

**Startup Flow:**
```python
# In bootstrap.py

def main():
    # ... existing setup ...
    
    # Create operator manager
    operator_manager = OperatorManager(Path("config/operators"))
    
    # Check for startup operator
    startup_op = operator_manager.get_startup_operator()
    
    if startup_op:
        config = operator_manager.load_operator(startup_op)
        if config:
            # Apply operator and skip HUB
            operator_manager.apply_operator(config, ui)
            ui.show()
            return app.exec()
    
    # No startup operator - show HUB
    host.mount_page("hub")
    ui.switch_page("hub")
    ui.show()
    
    return app.exec()
```

### 6.8 Vitals Display (Moved to HUB)

**Current Location:** Top-left of main window  
**New Location:** HUB page "SYSTEM STATUS" section

**Implementation:**
```python
# In PageHub._update_vitals()
def _update_vitals(self):
    import psutil
    
    cpu_percent = psutil.cpu_percent(interval=0.1)
    ram_used = psutil.virtual_memory().used / (1024**3)  # GB
    
    vitals_text = f"CPU: {cpu_percent:.1f}% | RAM: {ram_used:.1f}GB"
    self.lbl_vitals.setText(vitals_text)
    
    # Kernel status from AppState
    status_map = {
        SystemStatus.READY: ("READY", FG_ACCENT),
        SystemStatus.LOADING: ("LOADING", FG_WARN),
        SystemStatus.RUNNING: ("RUNNING", ACCENT_GOLD),
        SystemStatus.ERROR: ("ERROR", FG_ERROR),
        SystemStatus.UNLOADING: ("UNLOADING", FG_WARN),
    }
    
    status_text, status_color = status_map.get(
        self.state.status, ("UNKNOWN", FG_DIM)
    )
    
    self.lbl_kernel_status.setText(f"Status: {status_text}")
    self.lbl_kernel_status.setStyleSheet(f"color: {status_color}; font-size: 11px;")
```

---

## 7. OVERSEER DEBUG INTERFACE

### 7.1 Purpose

**Objective:** Real-time process monitoring and debugging for Monolith using viztracer

**Use Cases:**
- Track all function calls and execution timing
- Debug performance bottlenecks
- Monitor signal flow through kernel
- Capture errors with full stack traces
- Inspect token generation pipeline

### 7.2 Viztracer Integration

**Installation:**
```bash
pip install viztracer
```

**Pre-Filtering for Performance:**
Configure viztracer to exclude garbage BEFORE it hits the performance overhead:

```python
tracer = VizTracer(
    output_file="C:/Monolith/config/logs/trace_session.json",
    max_stack_depth=10,
    min_duration=5000,         # Only log functions >5ms (cuts noise by 80%)
    ignore_frozen=True,        # Skip Python stdlib
    exclude_files=[            # Skip dependencies
        "site-packages",
        "PySide6",
    ],
    log_func_args=False,       # Don't log arguments (reduces noise)
    log_sparse=True,           # Reduce overhead in production
    log_async=True,            # Async logging for minimal impact
    verbose=0
)
```

**Performance Impact:** ~2-3% overhead with pre-filtering (vs ~10% without)

**Launch Pattern:**
```python
# In bootstrap.py (or separate launcher)

from viztracer import VizTracer

def main():
    # Initialize viztracer
    tracer = VizTracer(
        output_file="config/logs/monolith_trace.json",
        max_stack_depth=10,
        min_duration=0.001,  # 1ms minimum
        verbose=0
    )
    
    tracer.start()
    
    try:
        # Run Monolith normally
        app = QApplication(sys.argv)
        # ... rest of bootstrap ...
        result = app.exec()
    finally:
        tracer.stop()
        tracer.save()
    
    return result
```

**Continuous Logging Mode:**
```python
# For long-running sessions, use rotating buffer
tracer = VizTracer(
    output_file="config/logs/monolith_trace_{}.json",
    max_stack_depth=10,
    log_sparse=True,  # Reduce overhead
    log_async=True,
)
```

### 7.3 Overseer UI Architecture

**Location:** System button in addon sidebar (outside addon panel)

**UI Type:** Separate window (QMainWindow)

**Implementation:**
```python
# ui/overseer_window.py

class OverseerWindow(QMainWindow):
    """Real-time debugging and process monitoring"""
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.log_dir = Path("config/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.setWindowTitle("Monolith Overseer")
        self.setGeometry(100, 100, 1200, 800)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Toolbar
        toolbar = QHBoxLayout()
        
        btn_refresh = QPushButton("⟳ Refresh")
        btn_refresh.clicked.connect(self._refresh_logs)
        
        btn_clear = QPushButton("× Clear")
        btn_clear.clicked.connect(self._clear_logs)
        
        self.chk_auto_scroll = QCheckBox("Auto-scroll")
        self.chk_auto_scroll.setChecked(True)
        
        self.chk_capture = QCheckBox("Enable Capture")
        self.chk_capture.setChecked(True)
        self.chk_capture.stateChanged.connect(self._toggle_capture)
        
        toolbar.addWidget(btn_refresh)
        toolbar.addWidget(btn_clear)
        toolbar.addWidget(self.chk_auto_scroll)
        toolbar.addWidget(self.chk_capture)
        toolbar.addStretch()
        
        layout.addLayout(toolbar)
        
        # Filter panel
        filter_panel = self._create_filter_panel()
        layout.addWidget(filter_panel)
        
        # Log display (command prompt style)
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet(f"""
            QTextEdit {{
                background: #000; 
                color: #0f0; 
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10px;
                border: none;
            }}
        """)
        layout.addWidget(self.log_display)
        
        # Status bar
        self.statusBar().showMessage("Overseer Active")
        
        # Start log monitor
        self._log_monitor_timer = QTimer(self)
        self._log_monitor_timer.timeout.connect(self._poll_logs)
        self._log_monitor_timer.start(500)  # Poll every 500ms
    
    def _create_filter_panel(self) -> QWidget:
        """Create filter controls"""
        panel = QGroupBox("Filters")
        layout = QHBoxLayout(panel)
        
        # Severity filters
        self.chk_error = QCheckBox("ERROR")
        self.chk_error.setChecked(True)
        self.chk_error.setStyleSheet(f"color: {FG_ERROR};")
        
        self.chk_warning = QCheckBox("WARNING")
        self.chk_warning.setChecked(True)
        self.chk_warning.setStyleSheet(f"color: {FG_WARN};")
        
        self.chk_info = QCheckBox("INFO")
        self.chk_info.setChecked(True)
        self.chk_info.setStyleSheet(f"color: {FG_TEXT};")
        
        self.chk_debug = QCheckBox("DEBUG")
        self.chk_debug.setChecked(False)
        self.chk_debug.setStyleSheet(f"color: {FG_DIM};")
        
        # Module filters
        self.inp_module_filter = QLineEdit()
        self.inp_module_filter.setPlaceholderText("Module filter (e.g., 'monokernel')")
        self.inp_module_filter.textChanged.connect(self._apply_filters)
        
        # Custom recipe
        self.combo_recipe = QComboBox()
        self.combo_recipe.addItems([
            "All Events",
            "Kernel Only",
            "Errors Only",
            "Performance Critical",
            "Custom"
        ])
        self.combo_recipe.currentTextChanged.connect(self._apply_recipe)
        
        layout.addWidget(QLabel("Show:"))
        layout.addWidget(self.chk_error)
        layout.addWidget(self.chk_warning)
        layout.addWidget(self.chk_info)
        layout.addWidget(self.chk_debug)
        layout.addWidget(QLabel("|"))
        layout.addWidget(QLabel("Module:"))
        layout.addWidget(self.inp_module_filter)
        layout.addWidget(QLabel("|"))
        layout.addWidget(QLabel("Recipe:"))
        layout.addWidget(self.combo_recipe)
        
        return panel
    
    def _poll_logs(self):
        """Poll SQLite database for new entries"""
        if not self.chk_capture.isChecked():
            return
        
        # Query recent events from SQLite
        try:
            db = OverseerDB(self.log_dir / "overseer.db")
            
            # Get events based on filters
            severities = []
            if self.chk_error.isChecked():
                severities.append("ERROR")
            if self.chk_warning.isChecked():
                severities.append("WARNING")
            if self.chk_info.isChecked():
                severities.append("INFO")
            if self.chk_debug.isChecked():
                severities.append("DEBUG")
            
            module_filter = self.inp_module_filter.text().strip()
            
            events = db.query_events(
                severities=severities if severities else None,
                category=module_filter if module_filter else None,
                limit=100
            )
            
            # Display new events
            for event in events:
                if self._is_new_event(event):
                    self._display_event(event)
        
        except Exception as e:
            pass  # Ignore query errors
    
    def _display_event(self, event: tuple):
        """Display single event row"""
        # event = (id, session_id, timestamp, severity, category, name, duration, message, metadata)
        event_id, session_id, timestamp, severity, category, name, duration, message, metadata = event
        
        color = self._severity_color(severity)
        
        log_line = f"[{severity}] {timestamp:.6f}s | {category}.{name} | {duration}μs"
        
        self.log_display.append(
            f"<span style='color:{color}'>{html.escape(log_line)}</span>"
        )
        
        if self.chk_auto_scroll.isChecked():
            self.log_display.verticalScrollBar().setValue(
                self.log_display.verticalScrollBar().maximum()
            )
        
        self._last_event_id = event_id
    
    def _is_new_event(self, event: tuple) -> bool:
        """Check if event hasn't been displayed yet"""
        event_id = event[0]
        if not hasattr(self, '_last_event_id'):
            self._last_event_id = 0
        return event_id > self._last_event_id
    
    def _classify_severity(self, event: dict) -> str:
        """Classify trace event severity"""
        name = event.get("name", "").lower()
        
        if "error" in name or "exception" in name:
            return "ERROR"
        elif "warn" in name:
            return "WARNING"
        elif event.get("dur", 0) > 100000:  # >100ms
            return "WARNING"
        else:
            return "INFO"
    
    def _severity_color(self, severity: str) -> str:
        return {
            "ERROR": "#ff4444",
            "WARNING": "#ffaa00",
            "INFO": "#00ff00",
            "DEBUG": "#888888"
        }.get(severity, "#00ff00")
    
    def _should_display_event(self, event: dict) -> bool:
        """Check if event passes filters"""
        severity = self._classify_severity(event)
        
        # Check severity filters
        if severity == "ERROR" and not self.chk_error.isChecked():
            return False
        if severity == "WARNING" and not self.chk_warning.isChecked():
            return False
        if severity == "INFO" and not self.chk_info.isChecked():
            return False
        
        # Check module filter
        module_filter = self.inp_module_filter.text().strip()
        if module_filter:
            cat = event.get("cat", "")
            if module_filter not in cat:
                return False
        
        return True
    
    def _apply_recipe(self, recipe_name: str):
        """Apply predefined filter recipe"""
        if recipe_name == "All Events":
            self.chk_error.setChecked(True)
            self.chk_warning.setChecked(True)
            self.chk_info.setChecked(True)
            self.chk_debug.setChecked(True)
            self.inp_module_filter.clear()
        
        elif recipe_name == "Kernel Only":
            self.chk_error.setChecked(True)
            self.chk_warning.setChecked(True)
            self.chk_info.setChecked(True)
            self.inp_module_filter.setText("monokernel")
        
        elif recipe_name == "Errors Only":
            self.chk_error.setChecked(True)
            self.chk_warning.setChecked(False)
            self.chk_info.setChecked(False)
            self.chk_debug.setChecked(False)
        
        elif recipe_name == "Performance Critical":
            # Show only slow operations
            self.chk_warning.setChecked(True)
            self.chk_info.setChecked(False)
    
    def _toggle_capture(self, state):
        """Enable/disable viztracer capture"""
        # This would communicate with main process to start/stop tracer
        pass
    
    def _refresh_logs(self):
        """Manually refresh log display"""
        self.log_display.clear()
        self._poll_logs()
    
    def _clear_logs(self):
        """Clear log display and files"""
        self.log_display.clear()
        
        # Optionally clear log files
        reply = QMessageBox.question(
            self, "Clear Logs",
            "Clear log files on disk?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            for log_file in self.log_dir.glob("*.json"):
                try:
                    log_file.unlink()
                except Exception:
                    pass
```

### 7.4 Addon Sidebar Integration

**Launch Button:**
```python
# In main_window.py (MonolithUI)

# Add system button to addon sidebar
btn_overseer = QPushButton("🔍 Overseer")
btn_overseer.setFixedHeight(40)
btn_overseer.setStyleSheet(f"""
    QPushButton {{
        background: {BG_SIDEBAR}; 
        color: {FG_TEXT}; 
        border: 1px solid {BORDER_DARK};
        text-align: left;
        padding-left: 10px;
        font-size: 11px;
    }}
    QPushButton:hover {{
        background: #1a1a1a; 
        border: 1px solid {ACCENT_GOLD};
    }}
""")
btn_overseer.clicked.connect(self._launch_overseer)

# Add to addon sidebar (outside normal addon list)
self.addon_sidebar_layout.addWidget(btn_overseer)

def _launch_overseer(self):
    if not hasattr(self, '_overseer_window') or not self._overseer_window.isVisible():
        self._overseer_window = OverseerWindow(self.state)
        self._overseer_window.show()
    else:
        self._overseer_window.activateWindow()
```

### 7.5 Log Storage Strategy

**Dual Storage System:**

1. **Viztracer Raw Dumps:** JSON (per-session, retained for 10 sessions)
   ```
   C:/Monolith/config/logs/trace_20250205_143022.json
   ```

2. **Overseer Processed Logs:** SQLite database (queryable, filterable)
   ```
   C:/Monolith/config/logs/overseer.db
   ```

**SQLite Schema:**
```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    severity TEXT NOT NULL,  -- ERROR, WARNING, INFO, DEBUG
    category TEXT,           -- Module name (monokernel, engine, ui)
    name TEXT,               -- Function name
    duration INTEGER,        -- Microseconds
    message TEXT,
    metadata TEXT            -- JSON blob for additional data
);

CREATE INDEX idx_severity ON events(severity);
CREATE INDEX idx_category ON events(category);
CREATE INDEX idx_timestamp ON events(timestamp);
CREATE INDEX idx_session ON events(session_id);
```

**Processing Pipeline:**
```python
import sqlite3
from pathlib import Path

class OverseerDB:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path)
        self._create_schema()
    
    def _create_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                severity TEXT NOT NULL,
                category TEXT,
                name TEXT,
                duration INTEGER,
                message TEXT,
                metadata TEXT
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_severity ON events(severity)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp)")
        self.conn.commit()
    
    def insert_event(self, session_id: str, event: dict):
        severity = self._classify_severity(event)
        self.conn.execute("""
            INSERT INTO events (session_id, timestamp, severity, category, name, duration, message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            event.get("ts", 0) / 1000000,
            severity,
            event.get("cat", ""),
            event.get("name", ""),
            event.get("dur", 0),
            f"{event.get('cat', '')}.{event.get('name', '')}"
        ))
    
    def query_events(self, severities=None, category=None, limit=1000):
        query = "SELECT * FROM events WHERE 1=1"
        params = []
        
        if severities:
            placeholders = ','.join('?' * len(severities))
            query += f" AND severity IN ({placeholders})"
            params.extend(severities)
        
        if category:
            query += " AND category LIKE ?"
            params.append(f"%{category}%")
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        return self.conn.execute(query, params).fetchall()
```

**Per-Session Logs:**
```python
# Generate unique log file per session
session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"config/logs/monolith_trace_{session_id}.json"
```

**Retention Policy:**
- Keep last 10 sessions
- Prune older logs on startup

```python
def prune_old_logs(log_dir: Path, keep_count: int = 10):
    log_files = sorted(log_dir.glob("monolith_trace_*.json"), 
                      key=lambda p: p.stat().st_mtime,
                      reverse=True)
    
    for old_file in log_files[keep_count:]:
        try:
            old_file.unlink()
        except Exception:
            pass
```

### 7.6 Performance Considerations

**Viztracer Overhead:**
- Minimal overhead in async mode (~5-10%)
- Use `log_sparse=True` for production
- Disable during normal operation, enable only when debugging

**Memory Usage:**
- Trace files can grow large (50-200MB for long sessions)
- Implement rotation: Close and open new file every 30 minutes
- Compress old trace files

```python
# Rotate trace files
def rotate_trace_file(tracer: VizTracer, session_id: str):
    tracer.stop()
    tracer.save()
    
    # Start new trace file
    new_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    tracer.output_file = f"config/logs/monolith_trace_{new_session_id}.json"
    tracer.start()
```

---

## 8. IMPLEMENTATION ORDER

### Phase 1: Foundation (Priority: CRITICAL)
1. **Config Path Consolidation**
   - Create C:\Monolith directory structure
   - Migrate all config paths to C:\Monolith\config\addons\
   - Add legacy path migration logic
   - Update bootstrap to create directories
   - **Estimated Effort:** 2-3 hours

2. **Config System Overhaul**
   - Implement user change tracking
   - Add Save/Reset buttons
   - Remove auto-save
   - GGUF metadata validation
   - **Estimated Effort:** 4-6 hours

3. **Bug Fixes**
   - Trace severity labeling (ERROR vs COMPLETE)
   - QTextEdit stylesheet (preserve for Overseer)
   - _topic_dominant heuristic adjustment
   - **Estimated Effort:** 1-2 hours

**Total Phase 1: 7-11 hours**

### Phase 2: Terminal Improvements (Priority: HIGH)
3. **Terminal UI Enhancements**
   - Right-aligned generation status with responsive wrapping
   - Date/time visibility control (Terminal-only)
   - Input bar enhancements ([+] Actions menu, Thinking mode toggle)
   - Operations panel restructuring (CONTROL/ARCHIVE/SETTINGS tabs)
   - **Estimated Effort:** 4-6 hours

4. **Message Actions System**
   - Migrate to QListWidget or add index tracking
   - Implement hover-reveal action buttons
   - Edit/Delete/Regen functionality
   - Undo system (input field only)
   - **Estimated Effort:** 8-12 hours

**Total Phase 2: 12-18 hours**

### Phase 3: Advanced Features (Priority: MEDIUM)
5. **Topic Generation**
   - Token counter integration
   - Two-phase title generation
   - Archive integration
   - **Estimated Effort:** 4-6 hours

6. **Operator System + HUB**
   - Create OperatorManager
   - Build HUB page addon
   - Operator CRUD operations
   - Bootstrap integration
   - **Estimated Effort:** 12-16 hours

### Phase 4: Debugging Tools (Priority: LOW)
7. **Overseer Debug Interface**
   - Viztracer integration with pre-filtering
   - SQLite database for processed logs
   - Overseer window implementation
   - Filter system and recipes
   - Addon sidebar button
   - **Estimated Effort:** 10-12 hours

**Total Phase 4: 10-12 hours**

---

## CRITICAL IMPLEMENTATION NOTES

### Kernel Contract Compliance
- **Every component** must follow Kernel Contract v2
- All execution goes through MonoBridge → MonoDock → MonoGuard
- NO direct engine calls from UI
- NO direct UI signals from engines
- HUB addon must use AddonContext for all kernel interaction

### File Organization
```
C:/Monolith/
├── config/
│   ├── addons/              # Addon-specific configs
│   │   ├── llm.json
│   │   ├── vision.json
│   │   └── audio.json
│   ├── operators/           # Operator presets
│   │   ├── default.json
│   │   ├── development.json
│   │   └── _startup.txt     # Startup operator name
│   └── logs/                # Overseer logs
│       ├── overseer.db      # SQLite database (queryable)
│       ├── trace_20250205_143022.json
│       └── trace_20250205_150415.json
├── models/                  # OPTIONAL: User model storage
└── outputs/                 # Generated content
    ├── images/
    └── audio/
```

### Testing Strategy
- Test each phase independently before moving to next
- Verify Kernel Contract compliance at each integration point
- Use Overseer to debug signal flows once implemented
- Test Operator save/load with various addon combinations

### Performance Targets
- Config save: <50ms
- Message action response: <100ms
- Operator load: <1s
- Overseer log processing: <10ms per event

---

## GLOSSARY

- **Addon**: Pluggable UI component (page or module)
- **Operator**: Saved workspace configuration
- **Session Config**: In-memory active configuration
- **Computer Change**: Programmatic config adjustment (not saved)
- **User Change**: Direct UI interaction (marked for saving)
- **Jenga Piece**: Cascading deletion of dependent messages
- **Phase 1/2 Title**: Initial vs refined topic generation
- **Overseer**: Debug monitoring interface using viztracer

---

**END OF SPECIFICATION**
