"""
toolbar.py — Gestion de toolbars indépendantes pour NoClicApp
"""
import customtkinter as ctk
from typing import List, Callable, Dict

class NoclicToolbar(ctk.CTkFrame):
    """Une toolbar personnalisée avec boutons associés à des macros."""
    
    def __init__(self, parent, app, config: List[Dict], **kwargs):
        super().__init__(parent, **kwargs)
        self.app = app
        self.config = config
        self.build()

    def build(self):
        self.grid_columnconfigure(0, weight=1)
        for i, btn_data in enumerate(self.config):
            btn = ctk.CTkButton(
                self,
                text=btn_data["label"],
                command=btn_data["command"],
                width=btn_data.get("width", 80),
                height=btn_data.get("height", 30),
                corner_radius=btn_data.get("corner_radius", 6),
                font=btn_data.get("font", ("Arial", 12)),
            )
            # Attache la clé pour compatibilité avec le système existant
            setattr(btn, "_ext_key", btn_data["key"])
            btn.grid(row=0, column=i, padx=2, pady=2, sticky="ew")
        self.grid_columnconfigure(len(self.config), weight=1)
        
    def destroy(self):
        """Nettoie la toolbar proprement."""
        super().destroy()
        if hasattr(self, 'app') and hasattr(self.app, 'toolbars'):
            if self in self.app.toolbars:
                self.app.toolbars.remove(self)