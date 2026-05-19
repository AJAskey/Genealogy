import json
import os
import tkinter as tk
from tkinter import ttk, messagebox


class JsonGuiExplorer:
    def __init__(self, root, initial_json_path):
        self.root = root
        self.root.title("Genealogy JSON Codebook Explorer")
        self.root.geometry("800x600")

        self.json_data = {}
        self.current_path = initial_json_path

        self.setup_ui()
        self.load_json(initial_json_path)

    def setup_ui(self):
        # Top Frame for File Info
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="File:").pack(side=tk.LEFT)
        self.file_label = ttk.Label(top_frame, text=os.path.basename(self.current_path), font=("Arial", 10, "bold"))
        self.file_label.pack(side=tk.LEFT, padx=5)

        # Search Frame
        search_frame = ttk.Frame(self.root, padding="5")
        search_frame.pack(fill=tk.X)
        ttk.Label(search_frame, text="Search Variables:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.filter_variables)
        ttk.Entry(search_frame, textvariable=self.search_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Main Paned Window
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Left Side: Variable List
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Variables").pack(anchor=tk.W)
        self.var_listbox = tk.Listbox(left_frame)
        self.var_listbox.pack(fill=tk.BOTH, expand=True)
        self.var_listbox.bind("<<ListboxSelect>>", self.on_variable_select)

        # Right Side: Details
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)

        ttk.Label(right_frame, text="Description:").pack(anchor=tk.W)
        self.desc_text = tk.Text(right_frame, height=3, state=tk.DISABLED, wrap=tk.WORD)
        self.desc_text.pack(fill=tk.X, pady=5)

        ttk.Label(right_frame, text="Codes & Labels:").pack(anchor=tk.W)

        # Treeview for Codes
        columns = ("code", "label")
        self.tree = ttk.Treeview(right_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("code", text="Code")
        self.tree.heading("label", text="Label")
        self.tree.column("code", width=100)
        self.tree.column("label", width=400)

        scrollbar = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bottom Frame for Actions
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(fill=tk.X)

        self.export_btn = ttk.Button(bottom_frame, text="Export Selected to 'selection.txt'",
                                     command=self.export_selection)
        self.export_btn.pack(side=tk.RIGHT)
        self.export_btn.config(state=tk.DISABLED)

    def export_selection(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("No Selection", "Please select a code/label from the list first.")
            return

        values = self.tree.item(selected_item[0], "values")
        code, label = values

        # Find which variable is currently selected in the listbox
        var_selection = self.var_listbox.curselection()
        if not var_selection:
            return
        var_name = self.var_listbox.get(var_selection[0])

        output_content = f"VARIABLE: {var_name}\nCODE: {code}\nLABEL: {label}\n"

        try:
            with open("selection.txt", "w") as f:
                f.write(output_content)
            messagebox.showinfo("Export Successful", f"Saved selection to selection.txt:\n\n{output_content}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to save file: {e}")

    def load_json(self, path):
        try:
            with open(path, 'r') as f:
                self.json_data = json.load(f)
            self.update_var_list()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load JSON: {e}")

    def update_var_list(self, filter_text=""):
        self.var_listbox.delete(0, tk.END)
        for var in sorted(self.json_data.keys()):
            if filter_text.lower() in var.lower():
                self.var_listbox.insert(tk.END, var)

    def filter_variables(self, *args):
        self.update_var_list(self.search_var.get())

    def on_variable_select(self, event):
        selection = self.var_listbox.curselection()
        if not selection:
            return

        var_name = self.var_listbox.get(selection[0])
        details = self.json_data.get(var_name, {})

        # Update Description
        self.desc_text.config(state=tk.NORMAL)
        self.desc_text.delete("1.0", tk.END)
        self.desc_text.insert(tk.END, details.get("description", "No description available."))
        self.desc_text.config(state=tk.DISABLED)

        # Update Codes Tree
        for item in self.tree.get_children():
            self.tree.delete(item)

        codes = details.get("codes", {})
        if isinstance(codes, dict):
            for code, label in sorted(codes.items()):
                self.tree.insert("", tk.END, values=(code, label))

        # Enable export button once list is loaded
        self.export_btn.config(state=tk.NORMAL)


if __name__ == "__main__":
    root = tk.Tk()
    # Path relative to project root
    json_path = os.path.join("../JSON", "codebook.json")
    app = JsonGuiExplorer(root, json_path)
    root.mainloop()
