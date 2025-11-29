import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import tool

# --- CONSTANTS & STYLES ---
COLORS = {
    "bg": "#1e1e2e",  # Dark Navy Background
    "card_bg": "#2a2a40",  # Lighter Navy for Cards
    "text": "#ffffff",  # White Text
    "subtext": "#a6a6c0",  # Greyish Text
    "accent": "#ff007f",  # Pink Accent
    "accent_hover": "#d6006b",
    "success": "#2e8b57",  # Sea Green
    "input_bg": "#3b3b55",
    "border": "#45455e",
}

FONTS = {
    "header": ("Segoe UI", 24, "bold"),
    "title": ("Segoe UI", 16, "bold"),
    "normal": ("Segoe UI", 10),
    "bold": ("Segoe UI", 10, "bold"),
    "small": ("Segoe UI", 9),
}


class StartupDialog(tk.Toplevel):
    def __init__(self, parent, state):
        super().__init__(parent, bg=COLORS["bg"])
        self.state = state
        self.title("Welcome")
        self.geometry("400x300")
        self.resizable(False, False)

        # Center on screen
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

        # Content
        ttk.Label(self, text="P.E.P", style="Header.TLabel").pack(pady=(40, 20))
        ttk.Label(
            self, text="Enter your Team ID to begin:", style="CardText.TLabel"
        ).pack(pady=(0, 10))

        self.id_entry = ttk.Entry(
            self,
            textvariable=self.state["team_id"],
            width=20,
            font=FONTS["title"],
            justify="center",
        )
        self.id_entry.pack(pady=10, ipady=5)
        self.id_entry.focus()
        self.id_entry.bind("<Return>", lambda e: self.validate_and_close())

        ttk.Button(self, text="Start Manager", command=self.validate_and_close).pack(
            pady=20
        )

        # Protocol to close app if X is clicked without ID
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.valid = False

    def validate_and_close(self):
        tid = self.state["team_id"].get().strip()
        if tid.isdigit():
            self.valid = True
            self.destroy()
        else:
            messagebox.showerror(
                "Error", "Please enter a valid numeric Team ID.", parent=self
            )

    def on_close(self):
        if not self.valid:
            self.master.destroy()


class FPLApp:
    def __init__(self, root):
        self.root = root
        self.root.title("P.E.P")
        self.root.geometry("1200x900")
        self.root.configure(bg=COLORS["bg"])

        self.setup_styles()

        self.manager = tool.FPLManager()

        # Shared State for Optimizer
        self.shared_state = {
            "team_id": tk.StringVar(),
            "optimization_data": None,
            "current_squad_ids": [],
            "current_squad_data": {},
            "status": "idle",
        }

        self.main_container = tk.Frame(root, bg=COLORS["bg"])
        self.main_container.pack(fill=tk.BOTH, expand=True)

        self.current_frame = None

        # Show Dialog
        self.root.withdraw()
        self.show_startup_dialog()

        # Start Optimization immediately
        tid = self.shared_state["team_id"].get()
        if tid:
            self.run_global_optimization(tid)

        self.show_dashboard()

    def show_startup_dialog(self):
        # Check for override file
        try:
            with open("team_id.txt", "r") as f:
                override_id = f.read().strip()
                if override_id.isdigit():
                    self.shared_state["team_id"].set(override_id)
                    print(f"Using Team ID from override file: {override_id}")
                    self.root.deiconify()
                    return
        except FileNotFoundError:
            pass

        dialog = StartupDialog(self.root, self.shared_state)
        self.root.wait_window(dialog)
        self.root.deiconify()

    def run_global_optimization(self, team_id):
        self.shared_state["status"] = "loading"
        thread = threading.Thread(
            target=self._optimization_thread, args=(int(team_id),)
        )
        thread.daemon = True
        thread.start()

    def _optimization_thread(self, team_id):
        try:
            starters, bench, captain, vice_captain, next_event = (
                self.manager.optimize_team(team_id)
            )

            self.shared_state["current_squad_ids"] = [p["id"] for p in starters + bench]
            self.shared_state["current_squad_data"] = {
                p["id"]: p for p in starters + bench
            }

            display_data = {
                "starters": starters,
                "bench": bench,
                "captain": captain,
                "vice_captain": vice_captain,
                "next_event": next_event,
            }
            self.shared_state["optimization_data"] = display_data
            self.root.after(0, self._optimization_complete)

        except Exception as e:
            print(f"Optimization error: {e}")
            self.root.after(0, lambda err=str(e): self._optimization_error(err))

    def _optimization_complete(self):
        self.shared_state["status"] = "done"
        if isinstance(self.current_frame, OptimizerBaseFrame):
            self.current_frame.optimization_complete(
                self.shared_state["optimization_data"]
            )

    def _optimization_error(self, error_msg):
        self.shared_state["status"] = "error"
        if isinstance(self.current_frame, OptimizerBaseFrame):
            self.current_frame.optimization_error(error_msg)

    def run_global_optimization_with_ids(self, player_ids):
        self.shared_state["status"] = "loading"
        thread = threading.Thread(
            target=self._optimization_thread_custom, args=(player_ids,)
        )
        thread.daemon = True
        thread.start()

    def _optimization_thread_custom(self, player_ids):
        try:
            starters, bench, captain, vice_captain, next_event = (
                self.manager.optimize_specific_squad(player_ids)
            )

            self.shared_state["current_squad_ids"] = [p["id"] for p in starters + bench]
            self.shared_state["current_squad_data"] = {
                p["id"]: p for p in starters + bench
            }

            display_data = {
                "starters": starters,
                "bench": bench,
                "captain": captain,
                "vice_captain": vice_captain,
                "next_event": next_event,
            }
            self.shared_state["optimization_data"] = display_data
            self.root.after(0, self._optimization_complete)

        except Exception as e:
            print(f"Optimization error: {e}")
            self.root.after(0, lambda err=str(e): self._optimization_error(err))

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        # General
        style.configure("TFrame", background=COLORS["bg"])
        style.configure(
            "TLabel",
            background=COLORS["bg"],
            foreground=COLORS["text"],
            font=FONTS["normal"],
        )
        style.configure(
            "Header.TLabel",
            font=FONTS["header"],
            foreground=COLORS["text"],
            background=COLORS["bg"],
        )
        style.configure(
            "SubHeader.TLabel",
            font=FONTS["title"],
            foreground=COLORS["text"],
            background=COLORS["bg"],
        )

        # Cards
        style.configure("Card.TFrame", background=COLORS["card_bg"])
        style.configure(
            "CardTitle.TLabel",
            background=COLORS["card_bg"],
            font=FONTS["title"],
            foreground=COLORS["text"],
        )
        style.configure(
            "CardText.TLabel",
            background=COLORS["card_bg"],
            font=FONTS["normal"],
            foreground=COLORS["subtext"],
        )

        # Buttons
        style.configure(
            "TButton",
            background=COLORS["accent"],
            foreground="white",
            borderwidth=0,
            font=FONTS["bold"],
            padding=10,
        )
        style.map("TButton", background=[("active", COLORS["accent_hover"])])

        style.configure(
            "Back.TButton", background=COLORS["card_bg"], foreground=COLORS["text"]
        )
        style.map("Back.TButton", background=[("active", COLORS["input_bg"])])

        # Inputs
        style.configure(
            "TEntry",
            fieldbackground=COLORS["input_bg"],
            foreground=COLORS["text"],
            insertcolor="white",
            borderwidth=0,
        )
        style.configure(
            "TCombobox",
            fieldbackground=COLORS["input_bg"],
            background=COLORS["input_bg"],
            foreground=COLORS["text"],
            arrowcolor="white",
        )

        # Treeview
        style.configure(
            "Treeview",
            background=COLORS["card_bg"],
            fieldbackground=COLORS["card_bg"],
            foreground=COLORS["text"],
            rowheight=30,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background=COLORS["input_bg"],
            foreground=COLORS["text"],
            font=FONTS["bold"],
            relief="flat",
        )
        style.map("Treeview", background=[("selected", COLORS["accent"])])

        # Labelframe
        style.configure(
            "TLabelframe",
            background=COLORS["bg"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
        )
        style.configure(
            "TLabelframe.Label",
            background=COLORS["bg"],
            foreground=COLORS["text"],
            font=FONTS["bold"],
        )

    def show_view(self, frame_class, *args, **kwargs):
        if self.current_frame:
            self.current_frame.destroy()

        self.current_frame = frame_class(self.main_container, self, *args, **kwargs)
        self.current_frame.pack(fill=tk.BOTH, expand=True)

    def show_dashboard(self):
        self.show_view(DashboardFrame)

    def show_transfer_hub(self):
        self.show_view(TransferFrame)

    def show_tactics_board(self):
        self.show_view(FormationFrame)

    def show_data_hub(self):
        self.show_view(DataFrame)

    def show_planner(self):
        self.show_view(PlannerFrame)

    def show_fdr(self):
        self.show_view(FDRFrame)

    def show_captaincy(self):
        self.show_view(CaptaincyFrame)


class DashboardFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller

        # Center Content
        content = tk.Frame(self, bg=COLORS["bg"])
        content.pack(expand=True)

        # Header
        header = ttk.Label(content, text="P.E.P", style="Header.TLabel")
        header.pack(pady=(0, 50))

        # Cards Container
        cards_frame = tk.Frame(content, bg=COLORS["bg"])
        cards_frame.pack()

        self.create_card(
            cards_frame,
            "Transfer Hub",
            "Scout players and analyze transfers",
            self.controller.show_transfer_hub,
            0,
        )
        self.create_card(
            cards_frame,
            "Tactics Board",
            "Visualize your team formation",
            self.controller.show_tactics_board,
            1,
        )
        self.create_card(
            cards_frame,
            "Data Hub",
            "Detailed statistical analysis",
            self.controller.show_data_hub,
            2,
        )

        self.create_card(
            cards_frame,
            "FPL Planner",
            "View upcoming fixtures for your squad",
            self.controller.show_planner,
            0,
            row=1,
        )
        self.create_card(
            cards_frame,
            "FDR Grid",
            "Fixture Difficulty Rating for all teams",
            self.controller.show_fdr,
            1,
            row=1,
        )
        self.create_card(
            cards_frame,
            "Captaincy",
            "Compare top captain picks",
            self.controller.show_captaincy,
            2,
            row=1,
        )

    def create_card(self, parent, title, subtitle, command, col, row=0):
        card = tk.Frame(
            parent, bg=COLORS["card_bg"], padx=30, pady=30, width=320, height=220
        )
        card.grid(row=row, column=col, padx=20, pady=20)

        card.pack_propagate(False)

        # Bind click events to everything in the card
        def on_click(e):
            command()

        card.bind("<Button-1>", on_click)

        lbl_title = ttk.Label(card, text=title, style="CardTitle.TLabel")
        lbl_title.pack(anchor="w", pady=(0, 10))
        lbl_title.bind("<Button-1>", on_click)

        lbl_sub = ttk.Label(
            card, text=subtitle, style="CardText.TLabel", wraplength=260
        )
        lbl_sub.pack(anchor="w")
        lbl_sub.bind("<Button-1>", on_click)

        # Hover effect
        def on_enter(e):
            card.config(bg=COLORS["input_bg"])
            lbl_title.configure(background=COLORS["input_bg"])
            lbl_sub.configure(background=COLORS["input_bg"])

        def on_leave(e):
            card.config(bg=COLORS["card_bg"])
            lbl_title.configure(background=COLORS["card_bg"])
            lbl_sub.configure(background=COLORS["card_bg"])

        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)


class BaseViewFrame(tk.Frame):
    def __init__(self, parent, controller, title):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller

        # Top Bar
        top_bar = tk.Frame(self, bg=COLORS["bg"], pady=20, padx=20)
        top_bar.pack(fill=tk.X)

        back_btn = ttk.Button(
            top_bar,
            text="← Back",
            style="Back.TButton",
            command=controller.show_dashboard,
        )
        back_btn.pack(side=tk.LEFT)

        header = ttk.Label(top_bar, text=title, style="SubHeader.TLabel")
        header.pack(side=tk.LEFT, padx=20)


class TransferFrame(BaseViewFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller, "Transfer Hub")

        self.manager = controller.manager

        # Main Content
        content = tk.Frame(self, bg=COLORS["bg"], padx=20)
        content.pack(fill=tk.BOTH, expand=True)

        # --- Inputs ---
        input_frame = tk.Frame(content, bg=COLORS["card_bg"], padx=20, pady=20)
        input_frame.pack(fill=tk.X, pady=(0, 20))

        ttk.Label(input_frame, text="Role:", style="CardText.TLabel").pack(
            side=tk.LEFT, padx=5
        )
        self.role_var = tk.StringVar()
        self.role_combo = ttk.Combobox(
            input_frame, textvariable=self.role_var, state="readonly", width=10
        )
        self.role_combo["values"] = ("ANY", "GK", "DEF", "MID", "FWD")
        self.role_combo.current(0)
        self.role_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(input_frame, text="Max Budget (£m):", style="CardText.TLabel").pack(
            side=tk.LEFT, padx=(20, 5)
        )
        self.budget_var = tk.StringVar(value="6.0")
        self.budget_entry = ttk.Entry(
            input_frame, textvariable=self.budget_var, width=10
        )
        self.budget_entry.pack(side=tk.LEFT, padx=5)

        self.analyze_btn = ttk.Button(
            input_frame, text="Analyze Market", command=self.start_analysis
        )
        self.analyze_btn.pack(side=tk.LEFT, padx=30)

        # Status
        self.status_var = tk.StringVar(value="Ready")
        self.status_lbl = ttk.Label(
            input_frame, textvariable=self.status_var, style="CardText.TLabel"
        )
        self.status_lbl.pack(side=tk.RIGHT)

        # Progress
        self.progress = ttk.Progressbar(
            content, orient=tk.HORIZONTAL, mode="indeterminate"
        )

        # --- Results Table ---
        columns = ("Name", "Team", "Price", "Form", "Predicted_Pts", "GW_Pts")
        self.tree = ttk.Treeview(content, columns=columns, show="headings")

        self.tree.heading("Name", text="Name")
        self.tree.heading("Team", text="Team")
        self.tree.heading("Price", text="Price")
        self.tree.heading("Form", text="Form")
        self.tree.heading("Predicted_Pts", text="Predicted Pts")
        self.tree.heading("GW_Pts", text="GW Points (Next 5)")

        self.tree.column("Name", width=150)
        self.tree.column("Team", width=100)
        self.tree.column("Price", width=80)
        self.tree.column("Form", width=60)
        self.tree.column("Predicted_Pts", width=100)
        self.tree.column("GW_Pts", width=250)

        scrollbar = ttk.Scrollbar(content, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)

    def start_analysis(self):
        try:
            budget = float(self.budget_var.get())
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid number for budget.")
            return

        role_str = self.role_var.get()
        role_map = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}
        role_id = role_map.get(role_str)

        self.analyze_btn.config(state=tk.DISABLED)
        self.progress.pack(fill=tk.X, pady=(0, 10))
        self.progress.start()
        self.status_var.set("Fetching data...")

        thread = threading.Thread(target=self.run_analysis, args=(role_id, budget))
        thread.daemon = True
        thread.start()

    def run_analysis(self, role_id, budget):
        try:
            teams, df_players = self.manager.fetch_and_filter_data(role_id, budget)

            if df_players.empty:
                self.after(0, self.analysis_complete, [])
                return

            candidates = df_players.sort_values(by="form", ascending=False).head(20)
            results = []
            total_candidates = len(candidates)

            for i, (_, player) in enumerate(candidates.iterrows()):
                self.after(
                    0,
                    self.status_var.set,
                    f"Analyzing {i + 1}/{total_candidates}: {player['web_name']}",
                )
                try:
                    time.sleep(0.05)
                    fixtures = self.manager.get_fixtures(player["id"])
                    xp, gw_points = self.manager.calculate_xp(player, teams, fixtures)
                    gw_str = ", ".join([f"{k}:{v}" for k, v in gw_points.items()])
                    results.append(
                        {
                            "Name": player["web_name"],
                            "Team": teams[player["team"]]["name"],
                            "Price": f"£{player['now_cost']}m",
                            "Form": player["form"],
                            "Predicted_Pts": round(xp, 2),
                            "GW_Pts": gw_str,
                        }
                    )
                except Exception as e:
                    print(f"Error analyzing {player['web_name']}: {e}")
                    continue

            final_results = sorted(
                results, key=lambda x: x["Predicted_Pts"], reverse=True
            )[:15]
            self.after(0, self.analysis_complete, final_results)

        except Exception as e:
            self.after(0, self.analysis_error, str(e))

    def analysis_complete(self, results):
        self.progress.stop()
        self.progress.pack_forget()
        self.analyze_btn.config(state=tk.NORMAL)
        self.status_var.set(f"Analysis complete. Found {len(results)} players.")

        for item in self.tree.get_children():
            self.tree.delete(item)

        for row in results:
            self.tree.insert(
                "",
                tk.END,
                values=(
                    row["Name"],
                    row["Team"],
                    row["Price"],
                    row["Form"],
                    row["Predicted_Pts"],
                    row["GW_Pts"],
                ),
            )

    def analysis_error(self, error_msg):
        self.progress.stop()
        self.progress.pack_forget()
        self.analyze_btn.config(state=tk.NORMAL)
        self.status_var.set("Error occurred.")
        messagebox.showerror("Analysis Error", error_msg)


class OptimizerBaseFrame(BaseViewFrame):
    """Shared logic for Formation and Data views"""

    def __init__(self, parent, controller, title):
        super().__init__(parent, controller, title)
        self.manager = controller.manager

        # Shared State Shortcuts
        self.state = controller.shared_state

        # --- Inputs ---
        self.input_frame = tk.Frame(self, bg=COLORS["card_bg"], padx=20, pady=20)
        self.input_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        # Display Team ID
        team_lbl = ttk.Label(
            self.input_frame,
            text=f"Team ID: {self.state['team_id'].get()}",
            style="CardTitle.TLabel",
        )
        team_lbl.pack(side=tk.LEFT, padx=5)

        self.gw_label = ttk.Label(self.input_frame, text="", style="CardTitle.TLabel")
        self.gw_label.pack(side=tk.RIGHT, padx=20)

        self.progress = ttk.Progressbar(
            self, orient=tk.HORIZONTAL, mode="indeterminate"
        )

    def check_initial_state(self):
        # Check State
        status = self.state.get("status", "idle")
        if status == "loading":
            self.progress.pack(fill=tk.X, padx=20, pady=(0, 10))
            self.progress.start()
        elif status == "done" and self.state["optimization_data"]:
            self.optimization_complete(self.state["optimization_data"])
        elif status == "error":
            messagebox.showerror("Error", "Optimization failed previously.")

    def optimization_complete(self, data):
        self.progress.stop()
        self.progress.pack_forget()

        next_event = data.get("next_event", "?")
        self.gw_label.config(text=f"Gameweek {next_event}")

        self.update_view(data)

    def optimization_error(self, error_msg):
        self.progress.stop()
        self.progress.pack_forget()
        messagebox.showerror("Optimization Error", error_msg)

    def update_view(self, data):
        pass  # To be implemented by subclasses


class FormationFrame(OptimizerBaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller, "Tactics Board")

        # Canvas
        self.pitch_canvas = tk.Canvas(self, bg=COLORS["success"], highlightthickness=0)
        self.pitch_canvas.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        # Load Image
        try:
            original_img = tk.PhotoImage(file="head.png")
            self.player_img = original_img.subsample(25, 25)
        except Exception as e:
            print(f"Error loading head.png: {e}")
            self.player_img = None

        self.check_initial_state()

        # Bind Resize
        self.pitch_canvas.bind("<Configure>", self.on_resize)

    def on_resize(self, event):
        if self.state["optimization_data"]:
            self.draw_pitch(self.state["optimization_data"])

    def update_view(self, data):
        self.draw_pitch(data)

    def draw_pitch(self, data):
        self.pitch_canvas.delete("all")
        w = self.pitch_canvas.winfo_width()
        h = self.pitch_canvas.winfo_height()
        if w < 100:
            w = 800
        if h < 100:
            h = 600

        # Draw Pitch Lines
        self.pitch_canvas.create_line(0, h * 0.8, w, h * 0.8, fill="white", width=2)
        self.pitch_canvas.create_text(
            w / 2, h * 0.82, text="BENCH", fill="white", font=FONTS["bold"]
        )

        # Group Starters
        gks = [p for p in data["starters"] if p["position"] == 1]
        defs = [p for p in data["starters"] if p["position"] == 2]
        mids = [p for p in data["starters"] if p["position"] == 3]
        fwds = [p for p in data["starters"] if p["position"] == 4]

        y_gk = h * 0.1
        y_def = h * 0.28
        y_mid = h * 0.48
        y_fwd = h * 0.68
        y_bench = h * 0.9

        self.draw_line(gks, y_gk, w, data)
        self.draw_line(defs, y_def, w, data)
        self.draw_line(mids, y_mid, w, data)
        self.draw_line(fwds, y_fwd, w, data)
        self.draw_line(data["bench"], y_bench, w, data)

    def draw_line(self, players, y, width, data):
        n = len(players)
        if n == 0:
            return
        gap = width / (n + 1)
        for i, p in enumerate(players):
            x = gap * (i + 1)
            self.draw_player(x, y, p, data)

    def draw_player(self, x, y, p, data):
        if self.player_img:
            self.pitch_canvas.create_image(
                x, y, image=self.player_img, anchor=tk.CENTER
            )
        else:
            self.pitch_canvas.create_oval(
                x - 15, y - 15, x + 15, y + 15, fill="white", outline="black"
            )

        self.pitch_canvas.create_text(
            x, y + 25, text=p["name"], fill="white", font=FONTS["bold"]
        )
        fixture_text = p.get("next_fixture", "-")
        self.pitch_canvas.create_text(
            x, y + 37, text=fixture_text, fill="#e0e0e0", font=FONTS["small"]
        )
        gw_xp_text = f"GW: {round(p['xp'], 1)}"
        self.pitch_canvas.create_text(
            x, y + 47, text=gw_xp_text, fill="#dddddd", font=FONTS["small"]
        )

        if p["id"] == data["captain"]["id"]:
            self.pitch_canvas.create_text(
                x + 20, y - 20, text="C", fill="yellow", font=("Segoe UI", 12, "bold")
            )
        elif p["id"] == data["vice_captain"]["id"]:
            self.pitch_canvas.create_text(
                x + 20, y - 20, text="V", fill="#cccccc", font=("Segoe UI", 10, "bold")
            )


class PlayerSearchDialog(tk.Toplevel):
    def __init__(
        self, parent, manager, on_select, initial_criteria=None, exclude_ids=None
    ):
        super().__init__(parent, bg=COLORS["bg"])
        self.manager = manager
        self.on_select = on_select
        self.exclude_ids = exclude_ids or []
        self.title("Player Search")
        self.geometry("1000x600")

        # Center
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

        # Search Bar
        search_frame = tk.Frame(self, bg=COLORS["bg"], pady=20)
        search_frame.pack(fill=tk.X, padx=20)

        self.search_var = tk.StringVar()
        entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        entry.pack(side=tk.LEFT, padx=(0, 10))
        entry.bind("<Return>", lambda e: self.start_search_thread())

        self.search_btn = ttk.Button(
            search_frame, text="Search", command=self.start_search_thread
        )
        self.search_btn.pack(side=tk.LEFT)

        # Status
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(
            search_frame, textvariable=self.status_var, style="CardText.TLabel"
        ).pack(side=tk.RIGHT)

        # Progress
        self.progress = ttk.Progressbar(
            self, orient=tk.HORIZONTAL, mode="indeterminate"
        )

        # Results
        columns = ("Name", "Team", "Price", "Form", "Predicted_Pts", "GW_Pts")
        self.tree = ttk.Treeview(self, columns=columns, show="headings")

        self.tree.heading("Name", text="Name")
        self.tree.heading("Team", text="Team")
        self.tree.heading("Price", text="Price")
        self.tree.heading("Form", text="Form")
        self.tree.heading("Predicted_Pts", text="Predicted Pts")
        self.tree.heading("GW_Pts", text="GW Points (Next 5)")

        self.tree.column("Name", width=150)
        self.tree.column("Team", width=100)
        self.tree.column("Price", width=80)
        self.tree.column("Form", width=60)
        self.tree.column("Predicted_Pts", width=100)
        self.tree.column("GW_Pts", width=250)

        self.tree.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        # Buttons
        btn_frame = tk.Frame(self, bg=COLORS["bg"], pady=20)
        btn_frame.pack(fill=tk.X, padx=20)

        ttk.Button(
            btn_frame, text="Select Player", command=self.confirm_selection
        ).pack(side=tk.RIGHT)
        ttk.Button(
            btn_frame, text="Cancel", command=self.destroy, style="Back.TButton"
        ).pack(side=tk.RIGHT, padx=10)

        if initial_criteria:
            self.after(100, lambda: self.start_auto_search_thread(initial_criteria))

    def start_auto_search_thread(self, criteria):
        self.search_btn.config(state=tk.DISABLED)
        self.progress.pack(fill=tk.X, pady=(0, 10), before=self.tree)
        self.progress.start()
        self.status_var.set("Auto-searching...")

        thread = threading.Thread(target=self.run_auto_search, args=(criteria,))
        thread.daemon = True
        thread.start()

    def run_auto_search(self, criteria):
        role_id = criteria.get("role_id")
        budget = criteria.get("budget", 999.0)

        try:
            # 1. Fetch Candidates
            _, df_players = self.manager.fetch_and_filter_data(role_id, budget)

            # Filter excluded
            if self.exclude_ids and not df_players.empty:
                df_players = df_players[~df_players["id"].isin(self.exclude_ids)]

            if df_players.empty:
                self.after(0, self.search_complete, [])
                return

            # 2. Sort and Take Top 20
            candidates = df_players.sort_values(by="form", ascending=False).head(20)

            # 3. Calculate XP
            results = self.calculate_xp_for_list(candidates)
            self.after(0, self.search_complete, results)

        except Exception as e:
            print(f"Auto-search error: {e}")
            self.after(0, self.search_error, str(e))

    def start_search_thread(self):
        query = self.search_var.get()
        if len(query) < 3:
            messagebox.showwarning("Search", "Please enter at least 3 characters.")
            return

        self.search_btn.config(state=tk.DISABLED)
        self.progress.pack(fill=tk.X, pady=(0, 10), before=self.tree)
        self.progress.start()
        self.status_var.set(f"Searching for '{query}'...")

        thread = threading.Thread(target=self.run_manual_search, args=(query,))
        thread.daemon = True
        thread.start()

    def run_manual_search(self, query):
        try:
            # 1. Search
            players_list = self.manager.search_player(query)

            # Filter excluded
            if self.exclude_ids:
                players_list = [
                    p for p in players_list if p["id"] not in self.exclude_ids
                ]

            if not players_list:
                self.after(0, self.search_complete, [])
                return

            # Convert to DataFrame for consistency with calculate_xp_for_list
            import pandas as pd

            df_players = pd.DataFrame(players_list)

            # 2. Calculate XP
            results = self.calculate_xp_for_list(df_players)
            self.after(0, self.search_complete, results)

        except Exception as e:
            print(f"Manual search error: {e}")
            self.after(0, self.search_error, str(e))

    def calculate_xp_for_list(self, df_players):
        results = []
        teams = self.manager.get_processed_teams()
        total = len(df_players)

        for i, (_, player) in enumerate(df_players.iterrows()):
            self.after(
                0,
                self.status_var.set,
                f"Analyzing {i + 1}/{total}: {player['web_name']}",
            )
            try:
                time.sleep(0.05)
                fixtures = self.manager.get_fixtures(player["id"])
                xp, gw_points = self.manager.calculate_xp(player, teams, fixtures)
                gw_str = ", ".join([f"{k}:{v}" for k, v in gw_points.items()])

                # Handle team name
                team_name = player.get("team_name")
                if not team_name and "team" in player:
                    team_name = teams[player["team"]]["name"]

                results.append(
                    {
                        "id": player["id"],
                        "Name": player["web_name"],
                        "Team": team_name,
                        "Price": f"£{player['now_cost']}m",
                        "Form": player["form"],
                        "Predicted_Pts": round(xp, 2),
                        "GW_Pts": gw_str,
                    }
                )
            except Exception as e:
                print(f"Error analyzing {player['web_name']}: {e}")
                continue

        # Sort by Predicted Points
        results.sort(key=lambda x: x["Predicted_Pts"], reverse=True)
        return results

    def search_complete(self, results):
        self.progress.stop()
        self.progress.pack_forget()
        self.search_btn.config(state=tk.NORMAL)
        self.status_var.set(f"Found {len(results)} players.")

        for item in self.tree.get_children():
            self.tree.delete(item)

        for row in results:
            self.tree.insert(
                "",
                tk.END,
                values=(
                    row["Name"],
                    row["Team"],
                    row["Price"],
                    row["Form"],
                    row["Predicted_Pts"],
                    row["GW_Pts"],
                ),
                tags=(str(row["id"]),),
            )

    def search_error(self, error_msg):
        self.progress.stop()
        self.progress.pack_forget()
        self.search_btn.config(state=tk.NORMAL)
        self.status_var.set("Error occurred.")
        messagebox.showerror("Search Error", error_msg)

    def confirm_selection(self):
        selected = self.tree.selection()
        if not selected:
            return

        item = self.tree.item(selected[0])
        if item["tags"]:
            player_id = int(item["tags"][0])
            self.on_select(player_id)
            self.destroy()


class DataFrame(OptimizerBaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller, "Data Hub")

        ttk.Button(
            self.input_frame, text="Simulate Transfer", command=self.on_transfer_click
        ).pack(side=tk.RIGHT, padx=20)

        # Table
        columns = (
            "Status",
            "Name",
            "Pos",
            "Price",
            "Mins% (L5)",
            "TSB%",
            "Def/90",
            "Pts/90 (L5)",
            "Pts/90/£m",
            "Total XP (5GW)",
            "Next 5 Fixtures",
        )
        self.tree = ttk.Treeview(self, columns=columns, show="headings")

        col_widths = {
            "Status": 60,
            "Name": 120,
            "Pos": 50,
            "Price": 60,
            "Mins% (L5)": 80,
            "TSB%": 60,
            "Def/90": 60,
            "Pts/90 (L5)": 80,
            "Pts/90/£m": 80,
            "Total XP (5GW)": 80,
            "Next 5 Fixtures": 300,
        }

        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=col_widths.get(col, 100), anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        self.check_initial_state()

        # Tags for Captaincy
        self.tree.tag_configure("captain", foreground="#FFD700")  # Gold
        self.tree.tag_configure("vice", foreground="#C0C0C0")  # Silver

    def update_view(self, data):
        for item in self.tree.get_children():
            self.tree.delete(item)

        all_players = []
        for p in data["starters"]:
            p["status"] = "Start"
            all_players.append(p)
        for p in data["bench"]:
            p["status"] = "Bench"
            all_players.append(p)

        all_players.sort(
            key=lambda x: (0 if x["status"] == "Start" else 1, x["position"])
        )

        cap_id = data["captain"]["id"] if data["captain"] else -1
        vice_id = data["vice_captain"]["id"] if data["vice_captain"] else -1

        for p in all_players:
            fixtures_str = " | ".join(
                [
                    f"{f['opponent']} ({round(f['xp'], 1)})"
                    for f in p.get("upcoming_fixtures", [])
                ]
            )

            display_name = p["name"]
            row_tag = ""

            if p["id"] == cap_id:
                display_name += " (C)"
                row_tag = "captain"
            elif p["id"] == vice_id:
                display_name += " (V)"
                row_tag = "vice"

            self.tree.insert(
                "",
                tk.END,
                iid=str(p["id"]),
                values=(
                    p["status"],
                    display_name,
                    self.get_pos_name(p["position"]),
                    f"£{p['price']}m",
                    f"{round(p.get('mins_percent_l5', 0), 1)}%",
                    f"{p.get('selected_by_percent', 0)}%",
                    round(p.get("def_per_90", 0), 2),
                    round(p.get("pts_per_90_l5", 0), 2),
                    round(p.get("pts_per_90_per_m_l5", 0), 2),
                    round(p.get("total_xp", 0), 2),
                    fixtures_str,
                ),
                tags=(row_tag,),
            )

    def on_transfer_click(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Transfer", "Please select a player to remove first.")
            return

        player_out_id = int(selected[0])

        # Get player details for auto-fill
        player_data = self.state["current_squad_data"].get(player_out_id)
        initial_criteria = None
        if player_data:
            initial_criteria = {
                "role_id": player_data["position"],
                "budget": player_data["price"],
            }

        PlayerSearchDialog(
            self,
            self.manager,
            lambda pid: self.perform_transfer(player_out_id, pid),
            initial_criteria=initial_criteria,
            exclude_ids=self.state.get("current_squad_ids", []),
        )

    def perform_transfer(self, player_out_id, player_in_id):
        current_ids = self.state["current_squad_ids"]
        if player_out_id in current_ids:
            new_ids = [pid for pid in current_ids if pid != player_out_id]
            new_ids.append(player_in_id)

            self.controller.run_global_optimization_with_ids(new_ids)
        else:
            messagebox.showerror("Error", "Player not found in current squad.")

    def get_pos_name(self, pos_id):
        return {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}.get(pos_id, "?")


class PlannerFrame(OptimizerBaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller, "FPL Planner")

        # Grid Container
        self.grid_frame = tk.Frame(self, bg=COLORS["bg"])
        self.grid_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        self.check_initial_state()

    def update_view(self, data):
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        # Headers
        headers = ["Player", "Pos"] + [f"GW{data['next_event'] + i}" for i in range(5)]
        for col, text in enumerate(headers):
            lbl = ttk.Label(
                self.grid_frame, text=text, style="CardTitle.TLabel", font=FONTS["bold"]
            )
            lbl.grid(row=0, column=col, padx=5, pady=10, sticky="w")

        # Rows
        all_players = data["starters"] + data["bench"]
        all_players.sort(key=lambda x: x["position"])

        for row_idx, p in enumerate(all_players, start=1):
            # Name
            ttk.Label(self.grid_frame, text=p["name"], style="CardText.TLabel").grid(
                row=row_idx, column=0, padx=5, pady=5, sticky="w"
            )
            # Pos
            pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
            ttk.Label(
                self.grid_frame, text=pos_map[p["position"]], style="CardText.TLabel"
            ).grid(row=row_idx, column=1, padx=5, pady=5, sticky="w")

            # Fixtures
            fixtures = p.get("upcoming_fixtures", [])
            for i in range(5):
                if i < len(fixtures):
                    f = fixtures[i]
                    # Color code based on difficulty (using XP as proxy for now, or just difficulty if we had it directly)
                    # We have XP. Low XP = Hard, High XP = Easy.
                    # Let's use a simple heuristic for color:
                    # We don't have raw difficulty in the 'upcoming_fixtures' dict in tool.py yet, only XP.
                    # But XP is better!

                    bg_color = COLORS["card_bg"]
                    fg_color = COLORS["text"]

                    # Simple XP heat map
                    if f["xp"] >= 6.0:
                        bg_color = COLORS["success"]  # Green
                    elif f["xp"] >= 4.0:
                        bg_color = "#88AA00"  # Light Green
                    elif f["xp"] >= 3.0:
                        bg_color = "#AAAA00"  # Yellowish
                    elif f["xp"] < 2.0:
                        bg_color = "#AA3333"  # Red

                    lbl = tk.Label(
                        self.grid_frame,
                        text=f"{f['opponent']}\n{round(f['xp'], 1)}",
                        bg=bg_color,
                        fg=fg_color,
                        width=10,
                        height=2,
                        font=FONTS["small"],
                    )
                    lbl.grid(row=row_idx, column=2 + i, padx=2, pady=2)
                else:
                    ttk.Label(self.grid_frame, text="-", style="CardText.TLabel").grid(
                        row=row_idx, column=2 + i, padx=5, pady=5
                    )


class FDRFrame(BaseViewFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller, "Fixture Difficulty Rating")
        self.manager = controller.manager

        self.content = tk.Frame(self, bg=COLORS["bg"])
        self.content.pack(fill=tk.BOTH, expand=True, padx=20)

        # Controls Frame
        controls_frame = tk.Frame(self.content, bg=COLORS["bg"])
        controls_frame.pack(fill=tk.X, pady=(0, 10))

        # Edit Button
        self.edit_btn = ttk.Button(
            controls_frame, text="Edit FDR", command=self.open_editor, state=tk.DISABLED
        )
        self.edit_btn.pack(side=tk.LEFT)

        # Horizon Controls
        tk.Label(
            controls_frame,
            text="Difficulty Horizon:",
            bg=COLORS["bg"],
            fg=COLORS["text"],
        ).pack(side=tk.LEFT, padx=(20, 5))

        self.horizon_var = tk.IntVar(value=5)
        spin = tk.Spinbox(
            controls_frame, from_=1, to=38, textvariable=self.horizon_var, width=5
        )
        spin.pack(side=tk.LEFT)

        ttk.Button(controls_frame, text="Update", command=self.refresh_grid).pack(
            side=tk.LEFT, padx=10
        )

        self.loading_lbl = ttk.Label(
            self.content, text="Loading FDR...", style="CardTitle.TLabel"
        )
        self.loading_lbl.pack(pady=20)

        # Load data in thread
        thread = threading.Thread(target=self.load_data)
        thread.daemon = True
        thread.start()

    def load_data(self):
        try:
            self.full_data = self.manager.get_all_team_fixtures()
            self.after(0, self.show_grid)
        except Exception as e:
            print(e)
            import traceback

            traceback.print_exc()

    def refresh_grid(self):
        if hasattr(self, "full_data"):
            self.show_grid()

    def show_grid(self):
        self.loading_lbl.destroy()
        self.edit_btn.config(state=tk.NORMAL)

        horizon = self.horizon_var.get()

        # Recalculate difficulty and sort
        display_data = []
        for team in self.full_data:
            # Calculate difficulty for the next 'horizon' fixtures
            relevant_fixtures = team["fixtures"][:horizon]
            total_diff = sum(f["difficulty"] for f in relevant_fixtures)

            # Create a copy to avoid modifying the original full_data in place repeatedly if we were to sort it
            # But here we just create a new list of dicts for display
            display_data.append(
                {
                    "team_name": team["team_name"],
                    "fixtures": team["fixtures"],  # Keep all fixtures for display
                    "total_difficulty": total_diff,
                }
            )

        # Sort by the new total_difficulty
        display_data.sort(key=lambda x: x["total_difficulty"])

        data = display_data

        # Create a specific frame for the grid to avoid pack/grid mix
        if hasattr(self, "grid_container"):
            self.grid_container.destroy()

        self.grid_container = tk.Frame(self.content, bg=COLORS["bg"])
        self.grid_container.pack(fill=tk.BOTH, expand=True)

        # Canvas for scrolling
        canvas = tk.Canvas(self.grid_container, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            self.grid_container, orient="horizontal", command=canvas.xview
        )

        self.grid_frame = tk.Frame(canvas, bg=COLORS["bg"])

        self.grid_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar.set)

        canvas.pack(side="top", fill="both", expand=True)
        scrollbar.pack(side="bottom", fill="x")

        # Headers
        headers = ["Team", "Difficulty"] + [
            f"GW{data[0]['fixtures'][i]['event']}"
            for i in range(len(data[0]["fixtures"]))
        ]

        for col, text in enumerate(headers):
            ttk.Label(
                self.grid_frame, text=text, style="CardTitle.TLabel", font=FONTS["bold"]
            ).grid(row=0, column=col, padx=5, pady=10)

        for row_idx, team in enumerate(data, start=1):
            ttk.Label(
                self.grid_frame, text=team["team_name"], style="CardText.TLabel"
            ).grid(row=row_idx, column=0, padx=5, pady=5, sticky="w")
            ttk.Label(
                self.grid_frame,
                text=str(team["total_difficulty"]),
                style="CardText.TLabel",
            ).grid(row=row_idx, column=1, padx=5, pady=5)

            for i, f in enumerate(team["fixtures"]):
                diff = f["difficulty"]
                color = "#2e8b57"  # Green (2)
                if diff == 3:
                    color = "#AAAA00"  # Yellowish
                elif diff == 4:
                    color = "#cc9900"  # Orange
                elif diff == 5:
                    color = "#cc3333"  # Red

                lbl = tk.Label(
                    self.grid_frame,
                    text=f"{f['opponent']}\n{'H' if f['is_home'] else 'A'}",
                    bg=color,
                    fg="white",
                    width=12,
                    height=2,
                    font=FONTS["small"],
                )
                lbl.grid(row=row_idx, column=2 + i, padx=2, pady=2)

                # Hover Effect
                self.create_tooltip(lbl, f"Difficulty: {diff}")

    def create_tooltip(self, widget, text):
        def enter(event):
            x, y, _, _ = widget.bbox("insert")
            x += widget.winfo_rootx() + 25
            y += widget.winfo_rooty() + 25

            self.tooltip = tk.Toplevel(widget)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{x}+{y}")

            label = tk.Label(
                self.tooltip,
                text=text,
                background="#ffffe0",
                relief="solid",
                borderwidth=1,
                font=FONTS["small"],
            )
            label.pack()

        def leave(event):
            if hasattr(self, "tooltip"):
                self.tooltip.destroy()

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def open_editor(self):
        FDREditorDialog(self, self.manager)


class FDREditorDialog(tk.Toplevel):
    def __init__(self, parent, manager):
        super().__init__(parent, bg=COLORS["bg"])
        self.manager = manager
        self.parent = parent
        self.title("Edit Team Difficulty")
        self.geometry("600x800")

        # Center
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

        # Header
        ttk.Label(self, text="Custom FDR Settings", style="Header.TLabel").pack(pady=20)
        ttk.Label(
            self,
            text="Set perceived difficulty (1-5) for each team.",
            style="CardText.TLabel",
        ).pack(pady=(0, 20))

        # Scrollable Frame
        container = tk.Frame(self, bg=COLORS["bg"])
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        canvas = tk.Canvas(container, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg=COLORS["bg"])

        self.scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Load Teams
        self.inputs = {}
        self.load_teams()

        # Buttons
        btn_frame = tk.Frame(self, bg=COLORS["bg"], pady=20)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="Save Changes", command=self.save_changes).pack(
            side=tk.RIGHT, padx=20
        )
        ttk.Button(
            btn_frame, text="Cancel", command=self.destroy, style="Back.TButton"
        ).pack(side=tk.RIGHT)

    def load_teams(self):
        data = self.manager.get_bootstrap_static()
        # Create a dict for easy lookup of strength
        teams_data = {t["name"]: t for t in data["teams"]}
        teams = sorted([t["name"] for t in data["teams"]])

        current_settings = self.manager.custom_fdr

        # Headers
        tk.Label(
            self.scrollable_frame,
            text="Team",
            bg=COLORS["bg"],
            fg=COLORS["text"],
            font=FONTS["bold"],
            width=20,
            anchor="w",
        ).grid(row=0, column=0, padx=5, pady=5)
        tk.Label(
            self.scrollable_frame,
            text="Home Strength",
            bg=COLORS["bg"],
            fg=COLORS["text"],
            font=FONTS["bold"],
        ).grid(row=0, column=1, padx=5, pady=5)
        tk.Label(
            self.scrollable_frame,
            text="Away Strength",
            bg=COLORS["bg"],
            fg=COLORS["text"],
            font=FONTS["bold"],
        ).grid(row=0, column=2, padx=5, pady=5)

        for i, team in enumerate(teams, start=1):
            tk.Label(
                self.scrollable_frame,
                text=team,
                bg=COLORS["bg"],
                fg=COLORS["text"],
                font=FONTS["normal"],
                anchor="w",
            ).grid(row=i, column=0, padx=5, pady=5, sticky="w")

            team_info = teams_data.get(team, {})
            # Default based on strength if available
            def_h = self.map_strength_to_fdr(
                team_info.get("strength_overall_home", 1100)
            )
            def_a = self.map_strength_to_fdr(
                team_info.get("strength_overall_away", 1100)
            )

            team_settings = current_settings.get(team, {})
            h_val = team_settings.get("H", def_h)
            a_val = team_settings.get("A", def_a)

            h_spin = tk.Spinbox(self.scrollable_frame, from_=1, to=5, width=5)
            h_spin.delete(0, "end")
            h_spin.insert(0, h_val)
            h_spin.grid(row=i, column=1, padx=5, pady=5)

            a_spin = tk.Spinbox(self.scrollable_frame, from_=1, to=5, width=5)
            a_spin.delete(0, "end")
            a_spin.insert(0, a_val)
            a_spin.grid(row=i, column=2, padx=5, pady=5)

            self.inputs[team] = (h_spin, a_spin)

    def map_strength_to_fdr(self, strength):
        if strength <= 1070:
            return 1
        if strength <= 1120:
            return 2
        if strength <= 1170:
            return 3
        if strength <= 1240:
            return 4
        return 5

    def save_changes(self):
        new_settings = {}
        for team, (h_spin, a_spin) in self.inputs.items():
            try:
                h = int(h_spin.get())
                a = int(a_spin.get())
                new_settings[team] = {"H": h, "A": a}
            except ValueError:
                pass

        self.manager.save_custom_fdr(new_settings)

        # Refresh Parent Grid
        for widget in self.parent.content.winfo_children():
            widget.destroy()

        self.parent.loading_lbl = ttk.Label(
            self.parent.content, text="Reloading FDR...", style="CardTitle.TLabel"
        )
        self.parent.loading_lbl.pack(pady=20)

        self.parent.edit_btn = ttk.Button(
            self.parent.content,
            text="Edit FDR",
            command=self.parent.open_editor,
            state=tk.DISABLED,
        )
        self.parent.edit_btn.pack(pady=(0, 20))

        thread = threading.Thread(target=self.parent.load_data)
        thread.daemon = True
        thread.start()

        self.destroy()


class CaptaincyFrame(BaseViewFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller, "Captaincy Picker")
        self.manager = controller.manager
        self.team_id = controller.shared_state["team_id"].get()

        self.content = tk.Frame(self, bg=COLORS["bg"])
        self.content.pack(fill=tk.BOTH, expand=True, padx=20)

        self.loading_lbl = ttk.Label(
            self.content, text="Analyzing Captains...", style="CardTitle.TLabel"
        )
        self.loading_lbl.pack(pady=20)

        thread = threading.Thread(target=self.load_data)
        thread.daemon = True
        thread.start()

    def load_data(self):
        try:
            candidates, next_gw = self.manager.get_captaincy_candidates(self.team_id)
            self.after(0, self.show_results, candidates, next_gw)
        except Exception as e:
            print(e)

    def show_results(self, candidates, next_gw):
        self.loading_lbl.destroy()

        ttk.Label(
            self.content, text=f"Top Picks for GW{next_gw}", style="Header.TLabel"
        ).pack(pady=(0, 20))

        container = tk.Frame(self.content, bg=COLORS["bg"])
        container.pack()

        for i, p in enumerate(candidates[:3]):
            card = tk.Frame(
                container, bg=COLORS["card_bg"], padx=20, pady=20, width=250
            )
            card.grid(row=0, column=i, padx=10)

            # Rank
            ttk.Label(
                card,
                text=f"#{i + 1}",
                style="Header.TLabel",
                foreground=COLORS["accent"],
            ).pack()

            # Name
            ttk.Label(card, text=p["name"], style="CardTitle.TLabel").pack(pady=5)

            # Team & Pos
            pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
            ttk.Label(
                card,
                text=f"{p['team']} - {pos_map[p['position']]}",
                style="CardText.TLabel",
            ).pack()

            # Score
            tk.Frame(card, height=2, bg=COLORS["border"]).pack(fill=tk.X, pady=10)

            self.row_stat(card, "Cap Score", round(p["cap_score"], 2), True)
            self.row_stat(card, "Predicted Pts", round(p["xp"], 2))
            self.row_stat(card, "Form", p["form"])
            self.row_stat(card, "Next", p["next_fixture"])

    def row_stat(self, parent, label, value, bold=False):
        f = tk.Frame(parent, bg=COLORS["card_bg"])
        f.pack(fill=tk.X, pady=2)
        ttk.Label(f, text=label, style="CardText.TLabel").pack(side=tk.LEFT)

        font = FONTS["bold"] if bold else FONTS["normal"]
        fg = COLORS["accent"] if bold else COLORS["text"]

        tk.Label(f, text=str(value), bg=COLORS["card_bg"], fg=fg, font=font).pack(
            side=tk.RIGHT
        )

    def get_pos_name(self, pos_id):
        return {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}.get(pos_id, "?")


if __name__ == "__main__":
    root = tk.Tk()
    app = FPLApp(root)
    root.mainloop()
