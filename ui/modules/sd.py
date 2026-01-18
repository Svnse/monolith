import os
import json
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QFrame, QScrollArea, QFileDialog, QSpinBox, QDoubleSpinBox,
    QCheckBox
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QImage

from core.style import BG_INPUT, BORDER_DARK, FG_DIM, FG_TEXT, FG_ACCENT, FG_ERROR
from ui.components.atoms import SkeetGroupBox, SkeetButton, CollapsibleSection

DIFFUSERS_AVAILABLE = False
try:
    import diffusers
    DIFFUSERS_AVAILABLE = True
except ImportError:
    pass


class SDWorker(QThread):
    progress = Signal(str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, prompt, model_path, steps, guidance, seed, use_seed):
        super().__init__()
        self.prompt = prompt
        self.model_path = model_path
        self.steps = steps
        self.guidance = guidance
        self.seed = seed if use_seed else None

    def run(self):
        try:
            import torch
            from diffusers import StableDiffusionPipeline
            
            self.progress.emit("Loading pipeline...")
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32
            
            pipe = StableDiffusionPipeline.from_pretrained(
                self.model_path,
                torch_dtype=dtype,
                safety_checker=None,
                requires_safety_checker=False
            )
            pipe = pipe.to(device)
            
            self.progress.emit("Generating image...")
            
            generator = None
            if self.seed is not None:
                generator = torch.Generator(device=device).manual_seed(self.seed)
            
            result = pipe(
                self.prompt,
                num_inference_steps=self.steps,
                guidance_scale=self.guidance,
                generator=generator
            )
            
            self.finished.emit(result.images[0])
            
        except Exception as e:
            self.error.emit(str(e))


class SDModule(QWidget):
    def __init__(self):
        super().__init__()
        
        self.config_path = Path("config/sd_config.json")
        self.artifacts_dir = Path("artifacts/vision")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.config = self._load_config()
        self.current_image = None
        self.worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        grp = SkeetGroupBox("STABLE DIFFUSION")
        inner = QVBoxLayout()
        inner.setSpacing(12)

        # Config Section
        config_section = CollapsibleSection("⚙ CONFIGURATION")
        config_layout = QVBoxLayout()
        config_layout.setSpacing(8)
        
        # Model Path
        model_row = QHBoxLayout()
        lbl_model = QLabel("Model Path")
        lbl_model.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")
        self.inp_model = QLineEdit(self.config.get("model_path", ""))
        self.inp_model.setPlaceholderText("Path to SD 1.5 model...")
        self.inp_model.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_INPUT}; color: {FG_TEXT};
                border: 1px solid {BORDER_DARK}; padding: 4px;
            }}
        """)
        btn_browse = SkeetButton("...")
        btn_browse.setFixedWidth(40)
        btn_browse.clicked.connect(self._browse_model)
        model_row.addWidget(lbl_model, 0)
        model_row.addWidget(self.inp_model, 1)
        model_row.addWidget(btn_browse, 0)
        config_layout.addLayout(model_row)
        
        # Steps
        steps_row = QHBoxLayout()
        lbl_steps = QLabel("Steps")
        lbl_steps.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")
        lbl_steps.setFixedWidth(80)
        self.inp_steps = QSpinBox()
        self.inp_steps.setRange(1, 150)
        self.inp_steps.setValue(self.config.get("steps", 25))
        self.inp_steps.setStyleSheet(f"""
            QSpinBox {{
                background: {BG_INPUT}; color: {FG_TEXT};
                border: 1px solid {BORDER_DARK}; padding: 4px;
            }}
        """)
        steps_row.addWidget(lbl_steps)
        steps_row.addWidget(self.inp_steps)
        steps_row.addStretch()
        config_layout.addLayout(steps_row)
        
        # Guidance Scale
        guidance_row = QHBoxLayout()
        lbl_guidance = QLabel("Guidance Scale")
        lbl_guidance.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")
        lbl_guidance.setFixedWidth(80)
        self.inp_guidance = QDoubleSpinBox()
        self.inp_guidance.setRange(1.0, 20.0)
        self.inp_guidance.setValue(self.config.get("guidance_scale", 7.5))
        self.inp_guidance.setSingleStep(0.5)
        self.inp_guidance.setStyleSheet(f"""
            QDoubleSpinBox {{
                background: {BG_INPUT}; color: {FG_TEXT};
                border: 1px solid {BORDER_DARK}; padding: 4px;
            }}
        """)
        guidance_row.addWidget(lbl_guidance)
        guidance_row.addWidget(self.inp_guidance)
        guidance_row.addStretch()
        config_layout.addLayout(guidance_row)
        
        # Seed
        seed_row = QHBoxLayout()
        self.chk_seed = QCheckBox("Use Seed")
        self.chk_seed.setChecked(self.config.get("use_seed", False))
        self.chk_seed.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")
        self.inp_seed = QSpinBox()
        self.inp_seed.setRange(0, 2147483647)
        self.inp_seed.setValue(self.config.get("seed", 42))
        self.inp_seed.setEnabled(self.chk_seed.isChecked())
        self.inp_seed.setStyleSheet(f"""
            QSpinBox {{
                background: {BG_INPUT}; color: {FG_TEXT};
                border: 1px solid {BORDER_DARK}; padding: 4px;
            }}
        """)
        self.chk_seed.toggled.connect(self.inp_seed.setEnabled)
        seed_row.addWidget(self.chk_seed)
        seed_row.addWidget(self.inp_seed)
        seed_row.addStretch()
        config_layout.addLayout(seed_row)
        
        btn_save_config = SkeetButton("SAVE CONFIG")
        btn_save_config.clicked.connect(self._save_config)
        config_layout.addWidget(btn_save_config)
        
        config_section.set_content_layout(config_layout)
        inner.addWidget(config_section)

        # Prompt
        lbl_prompt = QLabel("Prompt")
        lbl_prompt.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")

        self.inp_prompt = QLineEdit()
        self.inp_prompt.setPlaceholderText("Describe an image to generate...")
        self.inp_prompt.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_INPUT}; color: {FG_TEXT};
                border: 1px solid {BORDER_DARK}; padding: 6px;
            }}
        """)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_generate = SkeetButton("GENERATE", accent=True)
        self.btn_generate.clicked.connect(self._start_generate)
        self.btn_save = SkeetButton("SAVE IMAGE")
        self.btn_save.clicked.connect(self._save_image)
        self.btn_save.setEnabled(False)
        btn_row.addWidget(self.btn_generate)
        btn_row.addWidget(self.btn_save)
        btn_row.addStretch()

        # Preview
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setFixedHeight(400)
        preview_scroll.setStyleSheet(f"background: {BG_INPUT}; border: 1px solid {BORDER_DARK};")
        
        self.lbl_preview = QLabel("NO IMAGE")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setStyleSheet(f"color: {FG_DIM}; font-size: 12px;")
        preview_scroll.setWidget(self.lbl_preview)

        # Status
        status_row = QHBoxLayout()
        lbl_status_title = QLabel("Status")
        lbl_status_title.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")
        self.lbl_status = QLabel("IDLE")
        self.lbl_status.setStyleSheet(f"color: {FG_TEXT}; font-size: 10px; font-weight: bold;")
        status_row.addWidget(lbl_status_title)
        status_row.addStretch()
        status_row.addWidget(self.lbl_status)

        inner.addWidget(lbl_prompt)
        inner.addWidget(self.inp_prompt)
        inner.addLayout(btn_row)
        inner.addWidget(preview_scroll)
        inner.addLayout(status_row)
        inner.addStretch()

        grp.add_layout(inner)
        layout.addWidget(grp)

    def _load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            "model_path": "",
            "steps": 25,
            "guidance_scale": 7.5,
            "seed": 42,
            "use_seed": False
        }

    def _save_config(self):
        config = {
            "model_path": self.inp_model.text(),
            "steps": self.inp_steps.value(),
            "guidance_scale": self.inp_guidance.value(),
            "seed": self.inp_seed.value(),
            "use_seed": self.chk_seed.isChecked()
        }
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
        self.config = config
        self._set_status("CONFIG SAVED", FG_ACCENT)

    def _browse_model(self):
        path = QFileDialog.getExistingDirectory(self, "Select SD Model Directory")
        if path:
            self.inp_model.setText(path)

    def _set_status(self, status, color):
        self.lbl_status.setText(status)
        self.lbl_status.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: bold;")

    def _start_generate(self):
        if not DIFFUSERS_AVAILABLE:
            self._set_status("ERROR: diffusers not installed", FG_ERROR)
            return
            
        prompt = self.inp_prompt.text().strip()
        if not prompt:
            self._set_status("ERROR: No prompt", FG_ERROR)
            return
            
        model_path = self.inp_model.text().strip()
        if not model_path or not os.path.exists(model_path):
            self._set_status("ERROR: Invalid model path", FG_ERROR)
            return

        self.btn_generate.setEnabled(False)
        self.btn_save.setEnabled(False)
        self._set_status("INITIALIZING", FG_ACCENT)

        self.worker = SDWorker(
            prompt,
            model_path,
            self.inp_steps.value(),
            self.inp_guidance.value(),
            self.inp_seed.value(),
            self.chk_seed.isChecked()
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, msg):
        self._set_status(msg, FG_ACCENT)

    def _on_finished(self, pil_image):
        self.current_image = pil_image
        
        # Convert PIL to QPixmap
        pil_image = pil_image.convert("RGB")
        data = pil_image.tobytes("raw", "RGB")
        qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimage)
        
        self.lbl_preview.setPixmap(pixmap.scaled(
            self.lbl_preview.width() - 20,
            self.lbl_preview.height() - 20,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        ))
        
        self._set_status("DONE", FG_TEXT)
        self.btn_generate.setEnabled(True)
        self.btn_save.setEnabled(True)

    def _on_error(self, err_msg):
        self._set_status(f"ERROR: {err_msg}", FG_ERROR)
        self.btn_generate.setEnabled(True)

    def _save_image(self):
        if not self.current_image:
            return
            
        import time
        filename = f"sd_{int(time.time())}.png"
        filepath = self.artifacts_dir / filename
        
        try:
            self.current_image.save(filepath)
            self._set_status(f"SAVED: {filename}", FG_ACCENT)
        except Exception as e:
            self._set_status(f"SAVE ERROR: {str(e)}", FG_ERROR)