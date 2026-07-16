import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
from db import generate_key, list_keys, revoke_key

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timezone


class LicenseGenApp:
    DURATIONS = {
        "7 дней": 7,
        "14 дней": 14,
        "1 месяц": 30,
        "3 месяца": 90,
        "6 месяцев": 180,
        "12 месяцев": 365,
    }

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Qyouro — Управление ключами")
        self.root.geometry("900x650")
        self.root.resizable(True, True)
        self.root.configure(bg="#1a1a2e")

        self._build_generate_panel()
        self._build_search_bar()
        self._build_keys_table()
        self._refresh_table()

    def _build_generate_panel(self):
        frame = tk.Frame(self.root, bg="#1a1a2e", padx=12, pady=12)
        frame.pack(fill=tk.X)

        tk.Label(frame, text="Выпуск нового ключа", fg="#00ff88", bg="#1a1a2e",
                 font=("Segoe UI", 13, "bold")).pack(anchor=tk.W)

        row1 = tk.Frame(frame, bg="#1a1a2e")
        row1.pack(fill=tk.X, pady=8)

        tk.Label(row1, text="Организация:", fg="#ccc", bg="#1a1a2e",
                 font=("Segoe UI", 10), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.org_entry = tk.Entry(row1, bg="#16213e", fg="#fff", insertbackground="#fff",
                                   font=("Segoe UI", 10), relief=tk.FLAT, width=22)
        self.org_entry.pack(side=tk.LEFT, padx=6)

        tk.Label(row1, text="Телефон:", fg="#ccc", bg="#1a1a2e",
                 font=("Segoe UI", 10), width=10, anchor=tk.W).pack(side=tk.LEFT)
        self.phone_entry = tk.Entry(row1, bg="#16213e", fg="#fff", insertbackground="#fff",
                                     font=("Segoe UI", 10), relief=tk.FLAT, width=18)
        self.phone_entry.pack(side=tk.LEFT, padx=6)

        tk.Label(row1, text="Город:", fg="#ccc", bg="#1a1a2e",
                 font=("Segoe UI", 10), width=8, anchor=tk.W).pack(side=tk.LEFT)
        self.city_entry = tk.Entry(row1, bg="#16213e", fg="#fff", insertbackground="#fff",
                                    font=("Segoe UI", 10), relief=tk.FLAT, width=14)
        self.city_entry.pack(side=tk.LEFT)

        row2 = tk.Frame(frame, bg="#1a1a2e")
        row2.pack(fill=tk.X, pady=4)

        tk.Label(row2, text="Комментарий:", fg="#ccc", bg="#1a1a2e",
                 font=("Segoe UI", 10), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.comment_entry = tk.Entry(row2, bg="#16213e", fg="#fff", insertbackground="#fff",
                                       font=("Segoe UI", 10), relief=tk.FLAT, width=52)
        self.comment_entry.pack(side=tk.LEFT, padx=6)

        tk.Label(row2, text="Срок:", fg="#ccc", bg="#1a1a2e",
                 font=("Segoe UI", 10), width=6, anchor=tk.W).pack(side=tk.LEFT)
        self.dur_var = tk.StringVar(value="1 месяц")
        dur_menu = ttk.Combobox(row2, textvariable=self.dur_var, values=list(self.DURATIONS.keys()),
                                state="readonly", width=12, font=("Segoe UI", 10))
        dur_menu.pack(side=tk.LEFT, padx=6)

        gen_btn = tk.Button(row2, text="Создать ключ", bg="#00c853", fg="#fff",
                            font=("Segoe UI", 10, "bold"), relief=tk.FLAT,
                            padx=16, pady=4, cursor="hand2", command=self._generate)
        gen_btn.pack(side=tk.LEFT)

    def _build_search_bar(self):
        frame = tk.Frame(self.root, bg="#1a1a2e", padx=12, pady=8)
        frame.pack(fill=tk.X)

        tk.Label(frame, text="Поиск:", fg="#ccc", bg="#1a1a2e",
                 font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=6)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._refresh_table())
        search_entry = tk.Entry(frame, textvariable=self.search_var, bg="#16213e", fg="#fff",
                                insertbackground="#fff", font=("Segoe UI", 10),
                                relief=tk.FLAT, width=36)
        search_entry.pack(side=tk.LEFT, padx=6)

        tk.Label(frame, text="(по организации, телефону, городу, ключу)", fg="#666",
                 bg="#1a1a2e", font=("Segoe UI", 9)).pack(side=tk.LEFT)

        clear_btn = tk.Button(frame, text="Сброс", bg="#37474f", fg="#fff",
                              font=("Segoe UI", 9), relief=tk.FLAT, padx=10, pady=2,
                              cursor="hand2", command=lambda: [self.search_var.set(""), self._refresh_table()])
        clear_btn.pack(side=tk.RIGHT)

    def _build_keys_table(self):
        frame = tk.Frame(self.root, bg="#1a1a2e", padx=12)
        frame.pack(fill=tk.BOTH, expand=True, pady=8)

        toolbar = tk.Frame(frame, bg="#1a1a2e")
        toolbar.pack(fill=tk.X, pady=6)

        tk.Label(toolbar, text="Список ключей", fg="#00ff88", bg="#1a1a2e",
                 font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)

        revoke_btn = tk.Button(toolbar, text="Отозвать", bg="#c62828", fg="#fff",
                               font=("Segoe UI", 9), relief=tk.FLAT, padx=12, pady=3,
                               cursor="hand2", command=self._revoke)
        revoke_btn.pack(side=tk.RIGHT)

        refresh_btn = tk.Button(toolbar, text="Обновить", bg="#37474f", fg="#fff",
                                font=("Segoe UI", 9), relief=tk.FLAT, padx=12, pady=3,
                                cursor="hand2", command=self._refresh_table)
        refresh_btn.pack(side=tk.RIGHT, padx=8)

        columns = ("id", "key", "org", "phone", "city", "comment", "status", "created", "expires", "vk_id")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)

        self.tree.heading("id", text="ID")
        self.tree.heading("key", text="Ключ")
        self.tree.heading("org", text="Организация")
        self.tree.heading("phone", text="Телефон")
        self.tree.heading("city", text="Город")
        self.tree.heading("comment", text="Комментарий")
        self.tree.heading("status", text="Статус")
        self.tree.heading("created", text="Создан")
        self.tree.heading("expires", text="Истекает")
        self.tree.heading("vk_id", text="VK ID")

        self.tree.column("id", width=30, anchor=tk.CENTER)
        self.tree.column("key", width=140)
        self.tree.column("org", width=110)
        self.tree.column("phone", width=100)
        self.tree.column("city", width=80)
        self.tree.column("comment", width=100)
        self.tree.column("status", width=80, anchor=tk.CENTER)
        self.tree.column("created", width=80, anchor=tk.CENTER)
        self.tree.column("expires", width=80, anchor=tk.CENTER)
        self.tree.column("vk_id", width=70, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", self._copy_key)

    def _generate(self):
        org = self.org_entry.get().strip()
        if not org:
            messagebox.showwarning("Ошибка", "Введите название организации")
            return

        days = self.DURATIONS[self.dur_var.get()]
        phone = self.phone_entry.get().strip()
        city = self.city_entry.get().strip()
        comment = self.comment_entry.get().strip()

        key = generate_key(org, days, phone, city, comment)

        self.org_entry.delete(0, tk.END)
        self.phone_entry.delete(0, tk.END)
        self.city_entry.delete(0, tk.END)
        self.comment_entry.delete(0, tk.END)

        self._refresh_table()
        self.root.clipboard_clear()
        self.root.clipboard_append(key)
        messagebox.showinfo("Ключ создан",
                           f"Ключ: {key}\n\nОрганизация: {org}\nТелефон: {phone}\nГород: {city}\nСрок: {self.dur_var.get()}\n\nКлюч скопирован в буфер обмена.")

    def _refresh_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        search = self.search_var.get().strip()
        keys = list_keys(search=search)

        status_icons = {
            "active": "Активен",
            "expired": "Истёк",
            "revoked": "Отозван"
        }

        for k in keys:
            created = datetime.fromisoformat(k["created_at"]).strftime("%d.%m.%y")
            expires = datetime.fromisoformat(k["expires_at"]).strftime("%d.%m.%y")
            status_text = status_icons.get(k["status"], k["status"])
            if k["user_vk_id"]:
                status_text += " (актив.)"

            self.tree.insert("", tk.END, values=(
                k["id"],
                k["key"],
                k["organization_name"],
                k.get("phone", ""),
                k.get("city", ""),
                k.get("comment", ""),
                status_text,
                created,
                expires,
                k["user_vk_id"] or ""
            ))

    def _copy_key(self, event):
        sel = self.tree.selection()
        if sel:
            key = self.tree.item(sel[0], "values")[1]
            self.root.clipboard_clear()
            self.root.clipboard_append(key)

    def _revoke(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Ошибка", "Выберите ключ для отзыва")
            return
        key_id = int(self.tree.item(sel[0], "values")[0])
        ok = messagebox.askyesno("Подтверждение", f"Отозвать ключ #{key_id}?\n\nКлюч будет деактивирован и отвязан от пользователя.")
        if ok:
            revoke_key(key_id)
            self._refresh_table()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = LicenseGenApp()
    app.run()
