import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import requests

API_URL = "https://qyouro-1.onrender.com"


class QyouroAdminApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Qyouro Admin")
        self.root.geometry("920x680")
        self.root.minsize(800, 600)
        self.root.configure(bg="#1a1a2e")
        self.user = None
        self.role = None
        self.show_login()

    def clear(self):
        for w in self.root.winfo_children():
            w.destroy()

    def api(self, method, path, **kwargs):
        try:
            r = requests.request(method, f"{API_URL}{path}", timeout=15, **kwargs)
            return r.json()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Нет связи с сервером:\n{e}")
            return None

    # ─── LOGIN ────────────────────────────────────────────────────────

    def show_login(self):
        self.clear()
        self.root.configure(bg="#1a1a2e")

        frame = tk.Frame(self.root, bg="#1a1a2e")
        frame.place(relx=0.5, rely=0.4, anchor=tk.CENTER)

        tk.Label(frame, text="Qyouro Admin", fg="#00ff88", bg="#1a1a2e",
                 font=("Segoe UI", 28, "bold")).pack(pady=(0, 30))

        tk.Label(frame, text="Email:", fg="#ccc", bg="#1a1a2e",
                 font=("Segoe UI", 11)).pack(anchor=tk.W)
        email_entry = tk.Entry(frame, bg="#16213e", fg="#fff", font=("Segoe UI", 12),
                               relief=tk.FLAT, width=35, insertbackground="#fff")
        email_entry.pack(pady=(4, 12), ipady=6)

        tk.Label(frame, text="Пароль:", fg="#ccc", bg="#1a1a2e",
                 font=("Segoe UI", 11)).pack(anchor=tk.W)
        pass_entry = tk.Entry(frame, bg="#16213e", fg="#fff", font=("Segoe UI", 12),
                              relief=tk.FLAT, width=35, show="*", insertbackground="#fff")
        pass_entry.pack(pady=(4, 20), ipady=6)

        def do_login():
            email = email_entry.get().strip()
            password = pass_entry.get().strip()
            if not email or not password:
                messagebox.showwarning("Ошибка", "Заполните все поля")
                return
            result = self.api("post", "/api/auth/login", json={"email": email, "password": password})
            if result and result.get("ok"):
                self.user = result["user"]
                self.role = result["role"]
                self.show_main()
            else:
                messagebox.showerror("Ошибка", result.get("error", "Ошибка входа") if result else "Нет связи")

        login_btn = tk.Button(frame, text="Войти", bg="#00c853", fg="#fff",
                              font=("Segoe UI", 12, "bold"), relief=tk.FLAT,
                              width=35, height=2, cursor="hand2", command=do_login)
        login_btn.pack()

        reset_btn = tk.Button(frame, text="Забыли пароль?", bg="#1a1a2e", fg="#64b5f6",
                              font=("Segoe UI", 9), relief=tk.FLAT, cursor="hand2",
                              command=self.show_reset_password)
        reset_btn.pack(pady=(10, 0))

        # Check if admin exists
        result = self.api("get", "/api/auth/check-admin")
        if result and not result.get("exists"):
            reg_btn = tk.Button(frame, text="Регистрация администратора", bg="#1565c0", fg="#fff",
                                font=("Segoe UI", 10), relief=tk.FLAT, cursor="hand2",
                                command=self.show_register_admin)
            reg_btn.pack(pady=(20, 0))

        email_entry.focus()

    def show_register_admin(self):
        self.clear()
        frame = tk.Frame(self.root, bg="#1a1a2e")
        frame.place(relx=0.5, rely=0.35, anchor=tk.CENTER)

        tk.Label(frame, text="Регистрация администратора", fg="#00ff88", bg="#1a1a2e",
                 font=("Segoe UI", 18, "bold")).pack(pady=(0, 20))

        fields = [("Имя:", "name"), ("Email:", "email"), ("Пароль:", "password")]
        entries = {}
        for label, key in fields:
            tk.Label(frame, text=label, fg="#ccc", bg="#1a1a2e",
                     font=("Segoe UI", 11)).pack(anchor=tk.W)
            e = tk.Entry(frame, bg="#16213e", fg="#fff", font=("Segoe UI", 12),
                         relief=tk.FLAT, width=35, insertbackground="#fff",
                         show="*" if key == "password" else "")
            e.pack(pady=(4, 8), ipady=6)
            entries[key] = e

        def register():
            name = entries["name"].get().strip()
            email = entries["email"].get().strip()
            password = entries["password"].get().strip()
            if not all([name, email, password]):
                messagebox.showwarning("Ошибка", "Заполните все поля")
                return
            result = self.api("post", "/api/auth/register-admin",
                            json={"name": name, "email": email, "password": password})
            if result and result.get("ok"):
                messagebox.showinfo("Готово", "Администратор создан. Теперь войдите.")
                self.show_login()
            else:
                msg = result.get("error", "Ошибка") if result else "Нет связи"
                messagebox.showerror("Ошибка", msg)

        tk.Button(frame, text="Зарегистрировать", bg="#00c853", fg="#fff",
                  font=("Segoe UI", 12, "bold"), relief=tk.FLAT,
                  width=35, height=2, cursor="hand2", command=register).pack(pady=(10, 10))

        tk.Button(frame, text="← Назад", bg="#1a1a2e", fg="#64b5f6",
                  font=("Segoe UI", 10), relief=tk.FLAT, cursor="hand2",
                  command=self.show_login).pack()

    def show_reset_password(self):
        self.clear()
        frame = tk.Frame(self.root, bg="#1a1a2e")
        frame.place(relx=0.5, rely=0.35, anchor=tk.CENTER)

        tk.Label(frame, text="Восстановление пароля", fg="#00ff88", bg="#1a1a2e",
                 font=("Segoe UI", 18, "bold")).pack(pady=(0, 20))

        tk.Label(frame, text="Введите email для восстановления:", fg="#ccc", bg="#1a1a2e",
                 font=("Segoe UI", 11)).pack()
        email_entry = tk.Entry(frame, bg="#16213e", fg="#fff", font=("Segoe UI", 12),
                               relief=tk.FLAT, width=35, insertbackground="#fff")
        email_entry.pack(pady=(10, 20), ipady=6)

        status_label = tk.Label(frame, text="", fg="#ffc107", bg="#1a1a2e", font=("Segoe UI", 10))

        def send_reset():
            email = email_entry.get().strip()
            if not email:
                return
            result = self.api("post", "/api/auth/reset-password", json={"email": email})
            if result and result.get("ok"):
                status_label.config(text=f"Токен сброса: {result.get('token', '')[:20]}...\n"
                                        "(в production — отправка на email)")
                status_label.pack(pady=(10, 0))
                # Show token + new password fields
                tk.Label(frame, text="Токен (из email):", fg="#ccc", bg="#1a1a2e",
                         font=("Segoe UI", 11)).pack(anchor=tk.W, pady=(20, 0))
                token_entry = tk.Entry(frame, bg="#16213e", fg="#fff", font=("Segoe UI", 12),
                                       relief=tk.FLAT, width=35, insertbackground="#fff")
                token_entry.pack(pady=(4, 8), ipady=6)

                tk.Label(frame, text="Новый пароль:", fg="#ccc", bg="#1a1a2e",
                         font=("Segoe UI", 11)).pack(anchor=tk.W)
                newpass_entry = tk.Entry(frame, bg="#16213e", fg="#fff", font=("Segoe UI", 12),
                                         relief=tk.FLAT, width=35, show="*", insertbackground="#fff")
                newpass_entry.pack(pady=(4, 12), ipady=6)

                def apply_reset():
                    token = token_entry.get().strip()
                    newpass = newpass_entry.get().strip()
                    if not token or not newpass:
                        return
                    result2 = self.api("post", "/api/auth/reset-password",
                                     json={"token": token, "password": newpass})
                    if result2 and result2.get("ok"):
                        messagebox.showinfo("Готово", "Пароль изменён. Войдите.")
                        self.show_login()
                    else:
                        messagebox.showerror("Ошибка", "Неверный токен")

                tk.Button(frame, text="Сменить пароль", bg="#00c853", fg="#fff",
                          font=("Segoe UI", 11, "bold"), relief=tk.FLAT,
                          width=35, height=2, cursor="hand2",
                          command=apply_reset).pack(pady=(10, 10))
            else:
                messagebox.showerror("Ошибка", "Email не найден")

        tk.Button(frame, text="Отправить", bg="#1565c0", fg="#fff",
                  font=("Segoe UI", 11, "bold"), relief=tk.FLAT,
                  width=35, height=2, cursor="hand2", command=send_reset).pack()

        tk.Button(frame, text="← Назад", bg="#1a1a2e", fg="#64b5f6",
                  font=("Segoe UI", 10), relief=tk.FLAT, cursor="hand2",
                  command=self.show_login).pack(pady=(10, 0))

    # ─── MAIN SCREEN ──────────────────────────────────────────────────

    def show_main(self):
        self.clear()
        self.root.configure(bg="#1a1a2e")

        # Top bar
        top = tk.Frame(self.root, bg="#0d1117", height=50)
        top.pack(fill=tk.X)

        tk.Label(top, text=f"Qyouro Admin  |  {self.user.get('name') or self.user.get('fio')} ({self.role})",
                 fg="#fff", bg="#0d1117", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT, padx=16, pady=12)

        tk.Button(top, text="Выход", bg="#c62828", fg="#fff", font=("Segoe UI", 9),
                  relief=tk.FLAT, padx=14, pady=4, cursor="hand2",
                  command=lambda: [setattr(self, 'user', None), self.show_login()]).pack(side=tk.RIGHT, padx=16)

        # Tabs
        tab_frame = tk.Frame(self.root, bg="#1a1a2e")
        tab_frame.pack(fill=tk.X, padx=12, pady=(12, 0))

        tabs = [("Ключи", self.show_keys_tab), ("Сотрудники", self.show_employees_tab)]
        if self.role == "admin":
            tabs = [("Ключи", self.show_keys_tab), ("Сотрудники", self.show_employees_tab)]

        self.tab_buttons = []
        for i, (name, cmd) in enumerate(tabs):
            btn = tk.Button(tab_frame, text=name, bg="#16213e", fg="#ccc",
                           font=("Segoe UI", 10, "bold"), relief=tk.FLAT,
                           padx=20, pady=6, cursor="hand2",
                           command=lambda c=cmd: c())
            btn.pack(side=tk.LEFT, padx=(0, 4))
            self.tab_buttons.append(btn)

        self.content = tk.Frame(self.root, bg="#1a1a2e")
        self.content.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        self.show_keys_tab()

    def _switch_tab(self, idx):
        for i, btn in enumerate(self.tab_buttons):
            btn.config(bg="#00c853" if i == idx else "#16213e", fg="#000" if i == idx else "#ccc")

    def _clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()

    # ─── KEYS TAB ─────────────────────────────────────────────────────

    def show_keys_tab(self):
        self._switch_tab(0)
        self._clear_content()
        DURATIONS = {"7 дней": 7, "14 дней": 14, "1 месяц": 30, "3 месяца": 90,
                     "6 месяцев": 180, "12 месяцев": 365}

        gen_frame = tk.Frame(self.content, bg="#1a1a2e")
        gen_frame.pack(fill=tk.X, pady=(0, 8))

        r1 = tk.Frame(gen_frame, bg="#1a1a2e")
        r1.pack(fill=tk.X, pady=4)

        tk.Label(r1, text="Орг:", fg="#ccc", bg="#1a1a2e", font=("Segoe UI", 9), width=5, anchor=tk.W).pack(side=tk.LEFT)
        org_e = tk.Entry(r1, bg="#16213e", fg="#fff", font=("Segoe UI", 9), relief=tk.FLAT, width=18, insertbackground="#fff")
        org_e.pack(side=tk.LEFT, padx=2)

        tk.Label(r1, text="Тел:", fg="#ccc", bg="#1a1a2e", font=("Segoe UI", 9), width=4, anchor=tk.W).pack(side=tk.LEFT)
        phone_e = tk.Entry(r1, bg="#16213e", fg="#fff", font=("Segoe UI", 9), relief=tk.FLAT, width=14, insertbackground="#fff")
        phone_e.pack(side=tk.LEFT, padx=2)

        tk.Label(r1, text="Город:", fg="#ccc", bg="#1a1a2e", font=("Segoe UI", 9), width=6, anchor=tk.W).pack(side=tk.LEFT)
        city_e = tk.Entry(r1, bg="#16213e", fg="#fff", font=("Segoe UI", 9), relief=tk.FLAT, width=10, insertbackground="#fff")
        city_e.pack(side=tk.LEFT, padx=2)

        r2 = tk.Frame(gen_frame, bg="#1a1a2e")
        r2.pack(fill=tk.X, pady=4)

        tk.Label(r2, text="Комм:", fg="#ccc", bg="#1a1a2e", font=("Segoe UI", 9), width=5, anchor=tk.W).pack(side=tk.LEFT)
        cmt_e = tk.Entry(r2, bg="#16213e", fg="#fff", font=("Segoe UI", 9), relief=tk.FLAT, width=40, insertbackground="#fff")
        cmt_e.pack(side=tk.LEFT, padx=2)

        dur_var = tk.StringVar(value="1 месяц")
        ttk.Combobox(r2, textvariable=dur_var, values=list(DURATIONS.keys()),
                     state="readonly", width=12, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=4)

        def generate():
            org = org_e.get().strip()
            if not org:
                messagebox.showwarning("Ошибка", "Введите организацию")
                return
            result = self.api("post", "/api/generate-key", json={
                "organization_name": org, "expiry_days": DURATIONS[dur_var.get()],
                "phone": phone_e.get().strip(), "city": city_e.get().strip(),
                "comment": cmt_e.get().strip()
            })
            if result:
                org_e.delete(0, tk.END); phone_e.delete(0, tk.END)
                city_e.delete(0, tk.END); cmt_e.delete(0, tk.END)
                self.root.clipboard_clear(); self.root.clipboard_append(result["key"])
                refresh_table()
                messagebox.showinfo("Ключ создан", f"Ключ: {result['key']}\n\nСкопирован в буфер обмена.")

        tk.Button(r2, text="Создать", bg="#00c853", fg="#fff", font=("Segoe UI", 9, "bold"),
                  relief=tk.FLAT, padx=12, pady=2, cursor="hand2", command=generate).pack(side=tk.LEFT, padx=6)

        # Search + toolbar
        toolbar = tk.Frame(self.content, bg="#1a1a2e")
        toolbar.pack(fill=tk.X, pady=(4, 2))

        tk.Label(toolbar, text="Поиск:", fg="#ccc", bg="#1a1a2e", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        search_var = tk.StringVar()
        search_var.trace_add("write", lambda *a: refresh_table())
        tk.Entry(toolbar, textvariable=search_var, bg="#16213e", fg="#fff", font=("Segoe UI", 9),
                 relief=tk.FLAT, width=25, insertbackground="#fff").pack(side=tk.LEFT, padx=4)

        tk.Button(toolbar, text="Удалить", bg="#c62828", fg="#fff", font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=8, cursor="hand2",
                  command=lambda: delete_key()).pack(side=tk.RIGHT)
        tk.Button(toolbar, text="Отозвать", bg="#e65100", fg="#fff", font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=8, cursor="hand2",
                  command=lambda: revoke_key()).pack(side=tk.RIGHT, padx=3)

        # Table
        cols = ("id", "key", "org", "phone", "city", "comment", "status", "created", "expires", "vk_id")
        tree = ttk.Treeview(self.content, columns=cols, show="headings", height=10)
        for c in cols:
            tree.heading(c, text=c.upper() if c != "comment" else "КОММ")
        tree.column("id", width=30); tree.column("key", width=130); tree.column("org", width=100)
        tree.column("phone", width=90); tree.column("city", width=70); tree.column("comment", width=80)
        tree.column("status", width=80); tree.column("created", width=70)
        tree.column("expires", width=70); tree.column("vk_id", width=60)
        tree.pack(fill=tk.BOTH, expand=True)
        tree.bind("<Double-1>", lambda e: copy_key())

        def refresh_table():
            for row in tree.get_children():
                tree.delete(row)
            result = self.api("get", f"/api/keys?search={search_var.get()}")
            if not result:
                return
            for k in result.get("keys", []):
                st = {"active": "Активен", "expired": "Истёк", "revoked": "Отозван"}.get(k["status"], k["status"])
                if k["user_vk_id"]:
                    st += " (акт.)"
                tree.insert("", tk.END, values=(
                    k["id"], k["key"], k["organization_name"],
                    k.get("phone", ""), k.get("city", ""), k.get("comment", ""),
                    st, datetime.fromisoformat(k["created_at"]).strftime("%d.%m.%y"),
                    datetime.fromisoformat(k["expires_at"]).strftime("%d.%m.%y"),
                    k["user_vk_id"] or ""
                ))

        def copy_key():
            sel = tree.selection()
            if sel:
                self.root.clipboard_clear()
                self.root.clipboard_append(tree.item(sel[0], "values")[1])

        def revoke_key():
            sel = tree.selection()
            if not sel:
                return
            kid = int(tree.item(sel[0], "values")[0])
            if messagebox.askyesno("Подтверждение", f"Отозвать ключ #{kid}?"):
                self.api("post", "/api/revoke-key", json={"key_id": kid})
                refresh_table()

        def delete_key():
            sel = tree.selection()
            if not sel:
                return
            kid = int(tree.item(sel[0], "values")[0])
            if messagebox.askyesno("Подтверждение", f"Удалить ключ #{kid} безвозвратно?"):
                self.api("delete", f"/api/keys/{kid}")
                refresh_table()

        refresh_table()

    # ─── EMPLOYEES TAB ─────────────────────────────────────────────────

    def show_employees_tab(self):
        self._switch_tab(1)
        self._clear_content()

        # Add employee form
        form = tk.Frame(self.content, bg="#1a1a2e")
        form.pack(fill=tk.X, pady=(0, 8))

        fields = [
            ("ФИО:", "fio", 25), ("Email:", "email", 25),
            ("Пароль:", "password", 20), ("Телефон:", "phone", 15),
        ]
        row = tk.Frame(form, bg="#1a1a2e")
        row.pack(fill=tk.X, pady=4)
        entries = {}
        col_idx = 0
        for label, key, width in fields:
            f = tk.Frame(row, bg="#1a1a2e")
            f.pack(side=tk.LEFT, padx=4)
            tk.Label(f, text=label, fg="#ccc", bg="#1a1a2e", font=("Segoe UI", 8)).pack(anchor=tk.W)
            e = tk.Entry(f, bg="#16213e", fg="#fff", font=("Segoe UI", 9), relief=tk.FLAT,
                         width=width, insertbackground="#fff",
                         show="*" if key == "password" else "")
            e.pack()
            entries[key] = e
            col_idx += 1

        def add_employee():
            data = {k: v.get().strip() for k, v in entries.items()}
            if not data["fio"] or not data["email"] or not data["password"]:
                messagebox.showwarning("Ошибка", "Заполните ФИО, Email и Пароль")
                return
            result = self.api("post", "/api/employees", json=data)
            if result and result.get("ok"):
                for v in entries.values():
                    v.delete(0, tk.END)
                refresh_emp()
                messagebox.showinfo("Готово", "Сотрудник создан")
            else:
                messagebox.showerror("Ошибка", result.get("error", "Email занят") if result else "Нет связи")

        tk.Button(row, text="Добавить", bg="#00c853", fg="#fff", font=("Segoe UI", 9, "bold"),
                  relief=tk.FLAT, padx=14, pady=4, cursor="hand2", command=add_employee).pack(side=tk.LEFT, padx=6)

        # Toolbar
        toolbar = tk.Frame(self.content, bg="#1a1a2e")
        toolbar.pack(fill=tk.X, pady=(4, 2))

        tk.Button(toolbar, text="Сбросить пароль", bg="#1565c0", fg="#fff", font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=8, cursor="hand2",
                  command=lambda: reset_emp_pass()).pack(side=tk.RIGHT)
        tk.Button(toolbar, text="Удалить", bg="#c62828", fg="#fff", font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=8, cursor="hand2",
                  command=lambda: delete_emp()).pack(side=tk.RIGHT, padx=3)

        # Table
        cols = ("id", "email", "fio", "phone", "role", "status", "created")
        tree = ttk.Treeview(self.content, columns=cols, show="headings", height=12)
        for c in cols:
            tree.heading(c, text=c.upper() if c != "created" else "СОЗДАН")
        tree.column("id", width=30); tree.column("email", width=180); tree.column("fio", width=160)
        tree.column("phone", width=100); tree.column("role", width=80)
        tree.column("status", width=60); tree.column("created", width=80)
        tree.pack(fill=tk.BOTH, expand=True)

        def refresh_emp():
            for row in tree.get_children():
                tree.delete(row)
            result = self.api("get", "/api/employees")
            if not result:
                return
            for e in result.get("employees", []):
                tree.insert("", tk.END, values=(
                    e["id"], e["email"], e["fio"], e["phone"], e["role"], e["status"],
                    datetime.fromisoformat(e["created_at"]).strftime("%d.%m.%y")
                ))

        def delete_emp():
            sel = tree.selection()
            if not sel:
                return
            eid = int(tree.item(sel[0], "values")[0])
            name = tree.item(sel[0], "values")[2]
            if messagebox.askyesno("Подтверждение", f"Удалить сотрудника {name}?"):
                self.api("delete", f"/api/employees/{eid}")
                refresh_emp()

        def reset_emp_pass():
            sel = tree.selection()
            if not sel:
                return
            eid = int(tree.item(sel[0], "values")[0])
            name = tree.item(sel[0], "values")[2]
            new_pass = f"reset{datetime.now().strftime('%H%M')}"
            self.api("post", "/api/auth/reset-password", json={"emp_id": eid, "password": new_pass})
            messagebox.showinfo("Пароль сброшен", f"Сотрудник: {name}\nНовый пароль: {new_pass}\n\nСообщите сотруднику новый пароль.")

        refresh_emp()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = QyouroAdminApp()
    app.run()
