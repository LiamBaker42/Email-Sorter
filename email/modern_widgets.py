import tkinter as tk
from tkinter import ttk

class ModernButton(tk.Canvas):
    def __init__(self, parent, text, command=None, width=120, height=35,
                 bg="#4CAF50", fg="white", hover_bg="#45A049", radius=10, **kwargs):
        super().__init__(parent, width=width, height=height, bg=parent['bg'], highlightthickness=0, **kwargs)
        self.command = command
        self.bg = bg
        self.fg = fg
        self.hover_bg = hover_bg
        self.radius = radius

        self.rect = self.create_rounded_rect(0, 0, width, height, radius, fill=self.bg, outline="")
        self.text_item = self.create_text(width//2, height//2, text=text, fill=self.fg, font=("Helvetica", 10, "bold"))

        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)
        self.bind("<ButtonRelease-1>", self.on_release)

    def create_rounded_rect(self, x1, y1, x2, y2, r=25, **kwargs):
        points = [x1+r, y1,
                  x2-r, y1,
                  x2, y1,
                  x2, y1+r,
                  x2, y2-r,
                  x2, y2,
                  x2-r, y2,
                  x1+r, y2,
                  x1, y2,
                  x1, y2-r,
                  x1, y1+r,
                  x1, y1]
        return self.create_polygon(points, smooth=True, **kwargs)

    def on_enter(self, event):
        self.itemconfig(self.rect, fill=self.hover_bg)

    def on_leave(self, event):
        self.itemconfig(self.rect, fill=self.bg)

    def on_click(self, event):
        self.scale("all", self.winfo_width()//2, self.winfo_height()//2, 0.95, 0.95)

    def on_release(self, event):
        self.scale("all", self.winfo_width()//2, self.winfo_height()//2, 1/0.95, 1/0.95)
        if self.command:
            self.command()


class ModernEntry(tk.Frame):
    def __init__(self, parent, textvariable=None, width=25, bg="#ffffff", border_color="#ccc", **kwargs):
        super().__init__(parent, bg=bg, highlightthickness=1, highlightbackground=border_color, **kwargs)
        self.entry = tk.Entry(self, textvariable=textvariable, bd=0, relief="flat", font=("Helvetica", 10))
        self.entry.pack(fill="both", expand=True, padx=5, pady=3)
        self.configure(bg=bg)
        self.entry.bind("<FocusIn>", self.on_focus_in)
        self.entry.bind("<FocusOut>", self.on_focus_out)
        self.default_bg = bg
        self.focus_bg = "#e6f2ff"
    
    def get(self):
        return self.entry.get()
    
    def on_focus_in(self, event):
        self.configure(bg=self.focus_bg)
        self.entry.configure(bg=self.focus_bg)

    def on_focus_out(self, event):
        self.configure(bg=self.default_bg)
        self.entry.configure(bg=self.default_bg)


class ModernLabel(tk.Label):
    def __init__(self, parent, text, bg="#f0f0f0", fg="#333", font=("Helvetica", 10, "bold"), **kwargs):
        super().__init__(parent, text=text, bg=bg, fg=fg, font=font, **kwargs)


class ModernFrame(tk.Frame):
    def __init__(self, parent, bg="#f0f0f0", **kwargs):
        super().__init__(parent, bg=bg, **kwargs)


class ModernTreeview(ttk.Treeview):
    def __init__(self, parent, columns, show="headings", row_height=25, odd_bg="#ffffff", even_bg="#e6f2ff", **kwargs):
        super().__init__(parent, columns=columns, show=show, **kwargs)
        self.tag_configure('oddrow', background=odd_bg)
        self.tag_configure('evenrow', background=even_bg)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview.Heading", font=("Helvetica", 10, "bold"))
        style.configure("Treeview", rowheight=row_height, font=("Helvetica", 10))


class ModernScrollbar(ttk.Scrollbar):
    def __init__(self, parent, orient="vertical", **kwargs):
        super().__init__(parent, orient=orient, **kwargs)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Vertical.TScrollbar", troughcolor="#f0f0f0", background="#4CAF50",
                        arrowcolor="#4CAF50", bordercolor="#f0f0f0", lightcolor="#4CAF50", darkcolor="#4CAF50")
