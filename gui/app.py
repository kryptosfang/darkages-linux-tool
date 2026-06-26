import customtkinter as ctk
import tkinter as tk
import os
from state import state
from features.macro import (
    MacroFeature, 
    save_macros, 
    _normalize_trigger, 
    _parse_sequence, 
    Macro, 
    DEFAULT_STEP_DELAY,
    _SPECIAL_XDOTOOL
)
import threading
import asyncio
import uuid
import subprocess

def enable_linux_scroll(scrollable_frame: ctk.CTkScrollableFrame):
    """Explicitly bind mouse wheel buttons for Linux compatibility."""
    def on_scroll(event):
        if scrollable_frame.check_if_master_is_canvas(event.widget):
            if event.num == 4:
                scrollable_frame._parent_canvas.yview("scroll", -1, "units")
            elif event.num == 5:
                scrollable_frame._parent_canvas.yview("scroll", 1, "units")
    
    scrollable_frame.bind_all("<Button-4>", on_scroll, add="+")
    scrollable_frame.bind_all("<Button-5>", on_scroll, add="+")

class MacroEditor(ctk.CTkToplevel):
    def __init__(self, parent, on_save, macro_to_edit=None):
        super().__init__(parent)
        
        # Set icon
        try:
            self.icon_img = tk.PhotoImage(file='icon.png')
            self.wm_iconphoto(False, self.icon_img)
        except Exception:
            pass

        self.macro_to_edit = macro_to_edit
        self.title("Edit Macro/Keybind" if macro_to_edit else "New Configuration")
        self.geometry("650x900")
        self.on_save = on_save
        self.current_steps = list(macro_to_edit["steps"]) if macro_to_edit else []
        self.bound_trigger = macro_to_edit["trigger"] if macro_to_edit else None
        self.kind = macro_to_edit.get("kind", "macro") if macro_to_edit else "macro"
        self.trigger_mode = macro_to_edit.get("trigger_mode", "once") if macro_to_edit else "once"
        self.output_key = self.current_steps[0]["value"] if self.kind == "keybind" and self.current_steps else None
        self.listening_for = None # "trigger" or "output"
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self.title_label = ctk.CTkLabel(self, text="Configuration Editor", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(pady=20)
        
        self.main_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=30)
        enable_linux_scroll(self.main_container)

        # Mode Selector (Kind & Trigger)
        selector_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        selector_frame.pack(fill="x", pady=(0, 15))
        
        # Kind
        kind_frame = ctk.CTkFrame(selector_frame, fg_color="transparent")
        kind_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ctk.CTkLabel(kind_frame, text="Type:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.kind_selector = ctk.CTkSegmentedButton(kind_frame, values=["Macro", "Keybind"], command=self.toggle_kind)
        self.kind_selector.set("Macro" if self.kind == "macro" else "Keybind")
        self.kind_selector.pack(pady=(5, 0), fill="x")

        # Trigger Mode
        mode_frame = ctk.CTkFrame(selector_frame, fg_color="transparent")
        mode_frame.pack(side="left", fill="both", expand=True, padx=10)
        ctk.CTkLabel(mode_frame, text="Trigger Mode:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.mode_selector = ctk.CTkSegmentedButton(mode_frame, values=["Once", "Hold"])
        self.mode_selector.set("Once" if self.trigger_mode == "once" else "Hold")
        self.mode_selector.pack(pady=(5, 0), fill="x")

        # Interruptible Toggle
        int_frame = ctk.CTkFrame(selector_frame, fg_color="transparent")
        int_frame.pack(side="left", fill="both", expand=True, padx=(10, 0))
        ctk.CTkLabel(int_frame, text="Options:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        
        self.interrupt_var = ctk.BooleanVar(value=macro_to_edit.get("interruptible", True) if macro_to_edit else True)
        self.interrupt_switch = ctk.CTkSwitch(int_frame, text="Interrupt", variable=self.interrupt_var)
        self.interrupt_switch.pack(pady=(5, 0))

        self.enabled_var = ctk.BooleanVar(value=macro_to_edit.get("enabled", True) if macro_to_edit else True)
        self.enabled_switch = ctk.CTkSwitch(int_frame, text="Enabled", variable=self.enabled_var)
        self.enabled_switch.pack(pady=(5, 0))

        # Name Field
        ctk.CTkLabel(self.main_container, text="Name:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.name_entry = ctk.CTkEntry(self.main_container, placeholder_text="e.g. Buff Sequence", width=400)
        self.name_entry.pack(pady=(5, 15), anchor="w")
        if macro_to_edit: self.name_entry.insert(0, macro_to_edit["name"])

        # Trigger Field (Interactive)
        ctk.CTkLabel(self.main_container, text="Trigger Key:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        trigger_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        trigger_frame.pack(fill="x", pady=(5, 15))
        
        self.trigger_label = ctk.CTkLabel(trigger_frame, text=self.bound_trigger or "Not Bound", 
                                        fg_color="#333333", width=200, corner_radius=5)
        self.trigger_label.pack(side="left", padx=(0, 10))
        
        self.bind_btn = ctk.CTkButton(trigger_frame, text="Click to Bind", width=100, command=lambda: self.start_binding("trigger"))
        self.bind_btn.pack(side="left")

        # --- ACTION BUTTONS ---
        self.action_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.action_frame.pack(fill="x", pady=(10, 20))
        
        self.cancel_button = ctk.CTkButton(self.action_frame, text="Cancel", fg_color="gray", command=self.destroy)
        self.cancel_button.pack(side="left")
        
        self.save_button = ctk.CTkButton(self.action_frame, text="Save Configuration", command=self.save)
        self.save_button.pack(side="right")

        # --- KEYBIND MODE SECTION ---
        self.keybind_section = ctk.CTkFrame(self.main_container)
        
        ctk.CTkLabel(self.keybind_section, text="Direct Keybind Settings", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        
        ctk.CTkLabel(self.keybind_section, text="Output Key (What to send):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20)
        output_frame = ctk.CTkFrame(self.keybind_section, fg_color="transparent")
        output_frame.pack(fill="x", padx=20, pady=(5, 20))
        
        self.output_label = ctk.CTkLabel(output_frame, text=self.output_key or "Not Bound", 
                                       fg_color="#333333", width=200, corner_radius=5)
        self.output_label.pack(side="left", padx=(0, 10))
        
        self.output_bind_btn = ctk.CTkButton(output_frame, text="Click to Bind", width=100, command=lambda: self.start_binding("output"))
        self.output_bind_btn.pack(side="left")

        # --- STEP BUILDER SECTION ---
        self.macro_section = ctk.CTkFrame(self.main_container)
        
        ctk.CTkLabel(self.macro_section, text="Step Builder", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        # Quick Add Buttons
        quick_frame = ctk.CTkFrame(self.macro_section, fg_color="transparent")
        quick_frame.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkButton(quick_frame, text="Add Left Click", width=100, command=lambda: self.add_raw_step("mouse_left")).pack(side="left", padx=5)
        ctk.CTkButton(quick_frame, text="Add Right Click", width=100, command=lambda: self.add_raw_step("mouse_right")).pack(side="left", padx=5)
        
        self.record_btn = ctk.CTkButton(quick_frame, text="Record Window Click", fg_color="orange", text_color="black", hover_color="#CC8800",
                                       command=self.start_countdown)
        self.record_btn.pack(side="left", padx=5)

        # Input + Add Button
        input_frame = ctk.CTkFrame(self.macro_section, fg_color="transparent")
        input_frame.pack(fill="x", padx=20, pady=15)
        
        self.step_input = ctk.CTkEntry(input_frame, placeholder_text="Type keys (e.g. {enter}, f, {F1})...", width=350)
        self.step_input.pack(side="left", fill="x", expand=True)
        self.step_input.bind("<Return>", lambda e: self.add_segment())

        self.add_button = ctk.CTkButton(input_frame, text="Add Keys", width=80, command=self.add_segment)
        self.add_button.pack(side="left", padx=(10, 0))

        # Syntax Hint
        ctk.CTkLabel(self.macro_section, text="Syntax: {F1}, {enter}, {space}, {click}, {rclick}, {wait:100}", 
                    font=ctk.CTkFont(size=10), text_color="gray").pack(pady=(0, 10))

        # Capture Status Label
        self.capture_status = ctk.CTkLabel(self.macro_section, text="Status: Ready", font=ctk.CTkFont(size=11), text_color="gray")
        self.capture_status.pack(pady=(0, 5))

        # Manual Delay Setting
        delay_frame = ctk.CTkFrame(self.macro_section, fg_color="transparent")
        delay_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(delay_frame, text="Delay (ms):").pack(side="left")
        self.delay_input = ctk.CTkEntry(delay_frame, width=100, placeholder_text="100")
        self.delay_input.pack(side="left", padx=10)
        self.add_delay_btn = ctk.CTkButton(delay_frame, text="Add Delay Step", width=120, command=self.add_delay_step)
        self.add_delay_btn.pack(side="left")
        
        # Steps Display Area
        self.steps_display = ctk.CTkScrollableFrame(self.macro_section, label_text="Macro Stack", height=250)
        self.steps_display.pack(fill="both", expand=True, padx=20, pady=10)
        enable_linux_scroll(self.steps_display)
        
        self.refresh_steps_display()

        # Initial view setup
        self.toggle_kind(self.kind_selector.get())

        # Poll for captured clicks and triggers
        self.poll_state()

    def toggle_kind(self, value):
        self.kind = value.lower()
        if self.kind == "keybind":
            self.macro_section.pack_forget()
            self.keybind_section.pack(fill="both", expand=True, pady=10)
        else:
            self.keybind_section.pack_forget()
            self.macro_section.pack(fill="both", expand=True, pady=10)

    def start_binding(self, target):
        self.listening_for = target
        state["listening_for_trigger"] = True
        state["captured_trigger"] = None
        if target == "trigger":
            self.bind_btn.configure(text="Press Any Key...", state="disabled")
        else:
            self.output_bind_btn.configure(text="Press Any Key...", state="disabled")

    def poll_state(self):
        # 1. Check for captured triggers
        if state.get("captured_trigger"):
            key = state["captured_trigger"]
            state["captured_trigger"] = None
            state["listening_for_trigger"] = False
            
            if self.listening_for == "trigger":
                if key in ("BTN_LEFT", "CODE_272"):
                    self.capture_status.configure(text="Safety: Cannot bind Left Click as trigger!", text_color="red")
                    self.bind_btn.configure(text="Click to Bind", state="normal")
                    self.listening_for = None
                    return

                self.bound_trigger = key
                self.trigger_label.configure(text=self.bound_trigger)
                self.bind_btn.configure(text="Click to Bind", state="normal")
            elif self.listening_for == "output":
                # Convert evdev key to xdotool key
                from features.macro import _SPECIAL_XDOTOOL
                norm_key = key.replace("KEY_", "").lower()
                if norm_key in _SPECIAL_XDOTOOL:
                    self.output_key = _SPECIAL_XDOTOOL[norm_key]
                else:
                    self.output_key = norm_key
                self.output_label.configure(text=self.output_key)
                self.output_bind_btn.configure(text="Click to Bind", state="normal")
            
            self.listening_for = None

        # 2. Check for captured clicks
        if state.get("captured_click"):
            data = state["captured_click"]
            state["captured_click"] = None
            self.current_steps.append({
                "kind": data["kind"], "value": "", "delay_ms": 0, "x": data["x"], "y": data["y"]
            })
            self.capture_status.configure(text=f"Status: Captured click at {data['x']},{data['y']}", text_color="#44AA44")
            self.refresh_steps_display()

        # Reset record button if needed
        if not state.get("recording_mouse") and self.record_btn.cget("state") == "disabled":
            self.record_btn.configure(text="Record Window Click", state="normal")
        
        if self.winfo_exists():
            self.after(100, self.poll_state)

    def start_countdown(self, seconds=3):
        if seconds > 0:
            self.record_btn.configure(text=f"Click Game in {seconds}s...", state="disabled")
            self.capture_status.configure(text=f"Status: Move mouse to target in {seconds}s...", text_color="orange")
            self.after(1000, lambda: self.start_countdown(seconds - 1))
        else:
            self.perform_auto_capture()

    def perform_auto_capture(self):
        try:
            m_out = subprocess.check_output(["xdotool", "getmouselocation", "--shell"], stderr=subprocess.DEVNULL).decode()
            m_data = dict(line.split("=", 1) for line in m_out.strip().split("\n") if "=" in line)
            mx, my, mwid = int(m_data.get("X", 0)), int(m_data.get("Y", 0)), m_data.get("WINDOW")
            w_out = subprocess.check_output(["xdotool", "getwindowgeometry", "--shell", mwid], stderr=subprocess.DEVNULL).decode()
            w_data = dict(line.split("=", 1) for line in w_out.strip().split("\n") if "=" in line)
            wx, wy = int(w_data.get("X", 0)), int(w_data.get("Y", 0))

            self.current_steps.append({
                "kind": "mouse_left", "value": "", 
                "delay_ms": 0,
                "x": mx - wx, "y": my - wy
            })
            self.capture_status.configure(text=f"Status: Captured click at {mx-wx},{my-wy}", text_color="#44AA44")
        except Exception as e:
            self.capture_status.configure(text=f"Status: Capture failed: {str(e)}", text_color="red")
        self.record_btn.configure(text="Record Window Click", state="normal")
        self.refresh_steps_display()

    def add_raw_step(self, kind):
        self.current_steps.append({"kind": kind, "value": "", "delay_ms": 0})
        self.refresh_steps_display()

    def add_segment(self):
        seg = self.step_input.get().strip()
        if not seg: return
        new_steps = _parse_sequence(seg)
        self.current_steps.extend(new_steps)
        self.step_input.delete(0, 'end')
        self.refresh_steps_display()

    def add_delay_step(self):
        val = self.delay_input.get().strip()
        if not val.isdigit():
            self.delay_input.configure(border_color="red")
            return
        self.delay_input.configure(border_color="gray")
        ms = int(val)
        self.current_steps.append({"kind": "wait", "value": "", "delay_ms": ms})
        self.refresh_steps_display()

    def refresh_steps_display(self):
        for widget in self.steps_display.winfo_children(): widget.destroy()
        if not self.current_steps:
            ctk.CTkLabel(self.steps_display, text="Stack is empty.", text_color="gray").pack(pady=20)
            return
        for i, step in enumerate(self.current_steps):
            f = ctk.CTkFrame(self.steps_display)
            f.pack(fill="x", pady=2)
            
            if step["kind"] == "wait":
                label = f"WAIT {step['delay_ms']}ms"
                color = "orange"
            else:
                label = step["value"] if step["kind"] == "key" else f"[{step['kind']}]"
                color = "white"
                
            ctk.CTkLabel(f, text=f"{i+1}. {label}", font=ctk.CTkFont(family="monospace"), text_color=color).pack(side="left", padx=10)
            
            if step.get("x") is not None:
                ctk.CTkLabel(f, text=f"@{step['x']},{step['y']}", text_color="cyan", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=5)
            
            if step["kind"] != "wait" and step.get("delay_ms", 0) > 0:
                ctk.CTkLabel(f, text=f"{step['delay_ms']}ms", text_color="gray", font=ctk.CTkFont(size=10)).pack(side="left", padx=5)
            
            remove_btn = ctk.CTkButton(f, text="×", width=20, height=20, fg_color="transparent", text_color="red", hover_color="#331111", 
                                       command=lambda idx=i: self.remove_step(idx))
            remove_btn.pack(side="right", padx=5)

    def remove_step(self, index):
        if 0 <= index < len(self.current_steps):
            del self.current_steps[index]
            self.refresh_steps_display()

    def save(self):
        name = self.name_entry.get().strip() or "Unnamed"
        if not self.bound_trigger:
            self.title_label.configure(text="Trigger Key Required!", text_color="red")
            return
        
        if self.kind == "keybind":
            if not self.output_key:
                self.title_label.configure(text="Output Key Required!", text_color="red")
                return
            steps = [{"kind": "key", "value": self.output_key, "delay_ms": 0}]
        else:
            if not self.current_steps:
                self.title_label.configure(text="Stack is empty!", text_color="red")
                return
            steps = self.current_steps

        macro = Macro(
            id=self.macro_to_edit["id"] if self.macro_to_edit else str(uuid.uuid4()),
            name=name,
            enabled=self.enabled_var.get(),
            kind=self.kind,
            trigger_mode=self.mode_selector.get().lower(),
            trigger=self.bound_trigger,
            interruptible=self.interrupt_var.get(),
            steps=steps
        )
        self.on_save(macro)
        self.destroy()

class DarkAgesApp(ctk.CTk):
    def __init__(self, macro_feature: MacroFeature, loop: asyncio.AbstractEventLoop):
        super().__init__()

        # Set icon
        try:
            self.icon_img = tk.PhotoImage(file='icon.png')
            self.wm_iconphoto(False, self.icon_img)
        except Exception:
            pass

        self.macro_feature = macro_feature
        self.loop = loop
        self.title("DarkAges Linux Tool")
        self.geometry("900x800")
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Configure grid
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar / Navigation
        self.navigation_frame = ctk.CTkFrame(self, corner_radius=0)
        self.navigation_frame.grid(row=0, column=0, sticky="nsew")
        self.navigation_frame.grid_rowconfigure(4, weight=1)

        self.navigation_frame_label = ctk.CTkLabel(self.navigation_frame, text="DarkAges Linux Tool", 
                                                 font=ctk.CTkFont(size=15, weight="bold"))
        self.navigation_frame_label.grid(row=0, column=0, padx=20, pady=20)

        self.home_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10, text="Home",
                                       fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"),
                                       anchor="w", command=self.home_button_event)
        self.home_button.grid(row=1, column=0, sticky="ew")

        self.butterwalk_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10, text="Butterwalk",
                                              fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"),
                                              anchor="w", command=self.butterwalk_button_event)
        self.butterwalk_button.grid(row=2, column=0, sticky="ew")

        self.macro_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10, text="Macros",
                                         fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"),
                                         anchor="w", command=self.macro_button_event)
        self.macro_button.grid(row=3, column=0, sticky="ew")

        # Create frames
        self.home_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.butterwalk_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.macro_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        
        enable_linux_scroll(self.home_frame)
        enable_linux_scroll(self.butterwalk_frame)

        self._setup_home_frame()
        self._setup_butterwalk_frame()
        self._setup_macro_frame()

        # Select default frame
        self.select_frame_by_name("home")
        
        # Footer for monitoring
        self.footer_frame = ctk.CTkFrame(self, height=40, corner_radius=0)
        self.footer_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        
        self.footer_status = ctk.CTkLabel(self.footer_frame, text="○ Inactive", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray")
        self.footer_status.pack(side="left", padx=20)
        
        import input_hub
        kb, mice = input_hub.get_device_counts()
        self.footer_devices = ctk.CTkLabel(self.footer_frame, text=f"Devices: {kb} KB, {mice} Mice", font=ctk.CTkFont(size=11))
        self.footer_devices.pack(side="left", padx=10)
        
        self.footer_last_event = ctk.CTkLabel(self.footer_frame, text="Last Event: None", font=ctk.CTkFont(size=11, weight="bold"), text_color="orange")
        self.footer_last_event.pack(side="right", padx=20)
        
        # Start update loop
        self.update_gui()

    def _setup_home_frame(self):
        self.home_frame.grid_columnconfigure(0, weight=1)
        self.home_label = ctk.CTkLabel(self.home_frame, text="General Status", font=ctk.CTkFont(size=24, weight="bold"))
        self.home_label.pack(padx=20, pady=30)
        
        # Window Hooks Management
        hooks_container = ctk.CTkFrame(self.home_frame)
        hooks_container.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(hooks_container, text="Active Window Hooks:", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(10, 5))
        ctk.CTkLabel(hooks_container, text="(The tool will only arm when these titles are focused)", font=ctk.CTkFont(size=10), text_color="gray").pack()

        # Input to add new hook
        hook_input_frame = ctk.CTkFrame(hooks_container, fg_color="transparent")
        hook_input_frame.pack(fill="x", padx=20, pady=10)
        
        self.hook_entry = ctk.CTkEntry(hook_input_frame, placeholder_text="Enter Window Title...")
        self.hook_entry.pack(side="left", fill="x", expand=True)
        self.hook_entry.bind("<Return>", lambda e: self.add_hook())
        
        ctk.CTkButton(hook_input_frame, text="+ Add", width=60, command=self.add_hook).pack(side="left", padx=(10, 0))

        # List of hooks
        self.hooks_list_frame = ctk.CTkFrame(hooks_container, fg_color="transparent")
        self.hooks_list_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        self.refresh_hooks_display()

        # Input Suppression Toggle
        self.suppress_frame = ctk.CTkFrame(self.home_frame, fg_color="transparent")
        self.suppress_frame.pack(pady=20)
        
        self.suppress_switch = ctk.CTkSwitch(self.suppress_frame, text="Suppress Trigger Keys", 
                                            command=self.toggle_suppression,
                                            progress_color="orange")
        self.suppress_switch.pack(side="top")
        
        ctk.CTkLabel(self.suppress_frame, text="(Prevents trigger keys from reaching the game)", 
                    font=ctk.CTkFont(size=10), text_color="gray").pack(pady=5)

    def add_hook(self):
        val = self.hook_entry.get().strip()
        if val and val not in state["window_hooks"]:
            from state import save_config
            state["window_hooks"].append(val)
            self.hook_entry.delete(0, 'end')
            self.refresh_hooks_display()
            save_config()
        
    def remove_hook(self, val):
        if val in state["window_hooks"]:
            from state import save_config
            state["window_hooks"].remove(val)
            self.refresh_hooks_display()
            save_config()

    def refresh_hooks_display(self):
        for widget in self.hooks_list_frame.winfo_children(): widget.destroy()
        
        for hook in state["window_hooks"]:
            f = ctk.CTkFrame(self.hooks_list_frame, fg_color="#2B2B2B")
            f.pack(fill="x", pady=2)
            ctk.CTkLabel(f, text=hook).pack(side="left", padx=10)
            ctk.CTkButton(f, text="×", width=20, height=20, fg_color="transparent", text_color="red", 
                         hover_color="#331111", command=lambda v=hook: self.remove_hook(v)).pack(side="right", padx=5)

    def toggle_suppression(self):
        import input_hub
        from state import save_config
        enabled = self.suppress_switch.get() == 1
        state["suppress_triggers"] = enabled
        input_hub.toggle_suppression(enabled)
        save_config()

    def _setup_butterwalk_frame(self):
        self.bw_title = ctk.CTkLabel(self.butterwalk_frame, text="Butterwalk Settings", font=ctk.CTkFont(size=24, weight="bold"))
        self.bw_title.pack(padx=20, pady=30)

        self.bw_switch = ctk.CTkSwitch(self.butterwalk_frame, text="Enable Butterwalk", command=self.toggle_bw)
        self.bw_switch.pack(padx=20, pady=10)
        if state["butterwalk"]: self.bw_switch.select()

        self.zxcv_switch = ctk.CTkSwitch(self.butterwalk_frame, text="Enable ZXCV Mapping", command=self.toggle_zxcv)
        self.zxcv_switch.pack(padx=20, pady=10)
        if state["zxcv_enabled"]: self.zxcv_switch.select()

        self.dpad_switch = ctk.CTkSwitch(self.butterwalk_frame, text="Enable DPAD Mapping", command=self.toggle_dpad)
        self.dpad_switch.pack(padx=20, pady=10)
        if state["dpad_enabled"]: self.dpad_switch.select()

        self.space_switch = ctk.CTkSwitch(self.butterwalk_frame, text="Enable SPACE Mapping", command=self.toggle_space)
        self.space_switch.pack(padx=20, pady=10)
        if state["space_enabled"]: self.space_switch.select()

        self.multiplier_label = ctk.CTkLabel(self.butterwalk_frame, text=f"Multiplier: {state['multiplier']}x", font=ctk.CTkFont(size=16, weight="bold"))
        self.multiplier_label.pack(padx=20, pady=(30, 0))
        
        self.multiplier_slider = ctk.CTkSlider(self.butterwalk_frame, from_=1, to=5, number_of_steps=4, command=self.set_multiplier)
        self.multiplier_slider.set(state["multiplier"])
        self.multiplier_slider.pack(padx=20, pady=10, fill="x")

        self.input_display_label = ctk.CTkLabel(self.butterwalk_frame, text="Keys Pressed: —", font=ctk.CTkFont(family="monospace", size=14))
        self.input_display_label.pack(padx=20, pady=40)

    def _setup_macro_frame(self):
        self.macro_frame.grid_columnconfigure(0, weight=1)
        self.macro_frame.grid_rowconfigure(1, weight=1)

        self.macro_top_frame = ctk.CTkFrame(self.macro_frame, fg_color="transparent")
        self.macro_top_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        
        self.macro_title = ctk.CTkLabel(self.macro_top_frame, text="Macro Management", font=ctk.CTkFont(size=24, weight="bold"))
        self.macro_title.pack(side="left")
        
        self.new_macro_button = ctk.CTkButton(self.macro_top_frame, text="+ New Macro", command=self.open_editor)
        self.new_macro_button.pack(side="right")

        self.macro_list_frame = ctk.CTkScrollableFrame(self.macro_frame, label_text="Your Macros")
        self.macro_list_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        enable_linux_scroll(self.macro_list_frame)
        
        self.refresh_macro_list()

    def refresh_macro_list(self):
        for widget in self.macro_list_frame.winfo_children(): widget.destroy()
        
        macros_only = [m for m in state["macros"] if m.get("kind", "macro") == "macro"]
        binds_only = [m for m in state["macros"] if m.get("kind") == "keybind"]

        def render_section(title, items, color):
            if not items: return
            
            header = ctk.CTkFrame(self.macro_list_frame, fg_color="transparent")
            header.pack(fill="x", pady=(15, 5))
            ctk.CTkLabel(header, text=title, font=ctk.CTkFont(size=14, weight="bold"), text_color=color).pack(side="left", padx=10)
            ctk.CTkFrame(header, height=2, fg_color=color).pack(side="left", fill="x", expand=True, padx=10)

            for macro in items:
                item_frame = ctk.CTkFrame(self.macro_list_frame)
                item_frame.pack(fill="x", pady=2, padx=5)
                
                name_label = ctk.CTkLabel(item_frame, text=macro["name"], font=ctk.CTkFont(weight="bold"))
                name_label.pack(side="left", padx=10)
                
                trigger_label = ctk.CTkLabel(item_frame, text=macro["trigger"].replace("KEY_", ""), text_color="orange")
                trigger_label.pack(side="left", padx=10)
                
                steps_label = ctk.CTkLabel(item_frame, text=f"{len(macro['steps'])} steps", text_color="gray")
                steps_label.pack(side="left", padx=10)
                
                delete_btn = ctk.CTkButton(item_frame, text="Del", fg_color="#AA4444", hover_color="#882222", width=40, 
                                          command=lambda m=macro: self.delete_macro(m))
                delete_btn.pack(side="right", padx=10, pady=5)

                edit_btn = ctk.CTkButton(item_frame, text="Edit", width=40, fg_color="#4444AA",
                                        command=lambda m=macro: self.edit_macro(m))
                edit_btn.pack(side="right", padx=10, pady=5)

                enabled_switch = ctk.CTkSwitch(item_frame, text="", width=40, command=lambda m=macro: self.toggle_macro(m))
                if macro.get("enabled", True):
                    enabled_switch.select()
                enabled_switch.pack(side="right", padx=10)

        render_section("MACROS", macros_only, "gray70")
        render_section("KEYBINDS", binds_only, "cyan")

    def toggle_macro(self, macro):
        macro["enabled"] = not macro.get("enabled", True)
        save_macros()
        self.schedule_refresh()

    def open_editor(self):
        editor = MacroEditor(self, self.save_new_macro)
        editor.grab_set()

    def edit_macro(self, macro):
        editor = MacroEditor(self, self.save_edited_macro, macro_to_edit=macro)
        editor.grab_set()

    def save_new_macro(self, macro):
        state["macros"].append(macro)
        save_macros()
        self.schedule_refresh()
        self.macro_count_label.configure(text=f"Macros Loaded: {len(state['macros'])}")

    def delete_macro(self, macro):
        if macro in state["macros"]:
            state["macros"].remove(macro)
            save_macros()
            self.schedule_refresh()
            self.macro_count_label.configure(text=f"Macros Loaded: {len(state['macros'])}")

    def save_edited_macro(self, macro):
        for i, m in enumerate(state["macros"]):
            if m["id"] == macro["id"]:
                state["macros"][i] = macro
                break
        save_macros()
        self.schedule_refresh()

    def schedule_refresh(self):
        # Debounce refresh calls to prevent layout thrashing
        if hasattr(self, "_refresh_timer") and self._refresh_timer:
            self.after_cancel(self._refresh_timer)
        self._refresh_timer = self.after(100, self.refresh_macro_list)

    def play_macro(self, macro):
        if self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.macro_feature._play_macro(macro), self.loop)

    def select_frame_by_name(self, name):
        self.home_button.configure(fg_color=("gray75", "gray25") if name == "home" else "transparent")
        self.butterwalk_button.configure(fg_color=("gray75", "gray25") if name == "butterwalk" else "transparent")
        self.macro_button.configure(fg_color=("gray75", "gray25") if name == "macros" else "transparent")

        if name == "home": self.home_frame.grid(row=0, column=1, sticky="nsew")
        else: self.home_frame.grid_forget()
        
        if name == "butterwalk": self.butterwalk_frame.grid(row=0, column=1, sticky="nsew")
        else: self.butterwalk_frame.grid_forget()
        
        if name == "macros": self.macro_frame.grid(row=0, column=1, sticky="nsew")
        else: self.macro_frame.grid_forget()

    def home_button_event(self): self.select_frame_by_name("home")
    def butterwalk_button_event(self): self.select_frame_by_name("butterwalk")
    def macro_button_event(self): self.select_frame_by_name("macros")

    def toggle_bw(self): state["butterwalk"] = self.bw_switch.get() == 1
    def toggle_zxcv(self): 
        from state import save_config
        state["zxcv_enabled"] = self.zxcv_switch.get() == 1
        save_config()

    def toggle_dpad(self): 
        from state import save_config
        state["dpad_enabled"] = self.dpad_switch.get() == 1
        save_config()

    def toggle_space(self): 
        from state import save_config
        state["space_enabled"] = self.space_switch.get() == 1
        save_config()

    def set_multiplier(self, value): 
        from state import save_config
        state["multiplier"] = int(value)
        self.multiplier_label.configure(text=f"Multiplier: {state['multiplier']}x")
        save_config()

    def update_gui(self):
        # Update Footer Status
        status_text = "● ACTIVE" if state["active"] else "○ Inactive"
        status_color = "#44AA44" if state["active"] else "gray"
        self.footer_status.configure(text=status_text, text_color=status_color)
        
        # Sync switches if they were changed via hotkey
        if state["butterwalk"] and self.bw_switch.get() == 0: self.bw_switch.select()
        elif not state["butterwalk"] and self.bw_switch.get() == 1: self.bw_switch.deselect()
        
        if state["zxcv_enabled"] and self.zxcv_switch.get() == 0: self.zxcv_switch.select()
        elif not state["zxcv_enabled"] and self.zxcv_switch.get() == 1: self.zxcv_switch.deselect()

        if state["dpad_enabled"] and self.dpad_switch.get() == 0: self.dpad_switch.select()
        elif not state["dpad_enabled"] and self.dpad_switch.get() == 1: self.dpad_switch.deselect()

        if state["space_enabled"] and self.space_switch.get() == 0: self.space_switch.select()
        elif not state["space_enabled"] and self.space_switch.get() == 1: self.space_switch.deselect()
        
        self.multiplier_label.configure(text=f"Multiplier: {state['multiplier']}x")
        self.multiplier_slider.set(state["multiplier"])
        
        keys = ", ".join(k.replace("KEY_", "") for k in state["physical_keys_down"]) or "—"
        self.input_display_label.configure(text=f"Keys Pressed: {keys}")
        
        # Update Footer Monitoring
        self.footer_last_event.configure(text=f"Last Event: {state['last_event']}")

        if state["running"]:
            self.after(200, self.update_gui)

def run_gui(macro_feature, loop):
    app = DarkAgesApp(macro_feature, loop)
    def on_closing():
        state["running"] = False
        app.destroy()
    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()
