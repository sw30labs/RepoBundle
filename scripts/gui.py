#!/usr/bin/env python3
# =========================================================================
# gui.py
# =========================================================================
# Raycast-inspired GUI for RepoBundle.
# =========================================================================

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from export_repo import default_output_path, export_repository
from import_repo import restore_repository


COLORS = {
    'bg': '#07080a',
    'surface': '#101111',
    'surface_alt': '#1b1c1e',
    'border': '#252829',
    'text': '#f9f9f9',
    'muted': '#9c9c9d',
    'dim': '#6a6b6c',
    'accent': '#ff6363',
    'info': '#55b3ff',
    'danger': '#ff6363',
    'entry': '#0d0e10',
}


def format_bytes(size):
    units = ['B', 'KB', 'MB', 'GB']
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != 'B' else f"{int(value)} {unit}"
        value /= 1024


def open_path(path):
    if sys.platform == 'darwin':
        subprocess.Popen(['open', str(path)])
    elif os.name == 'nt':
        os.startfile(str(path))
    else:
        subprocess.Popen(['xdg-open', str(path)])


class RepoBundleApp:
    def __init__(self, root):
        self.root = root
        self.root.title('RepoBundle')
        self.root.geometry('980x720')
        self.root.minsize(760, 560)
        self.root.configure(bg=COLORS['bg'])

        self.events = queue.Queue()
        self.mode = 'export'
        self.busy = False
        self.last_export_path = None
        self.last_restore_dir = None
        self.controls = []

        cwd = Path.cwd()
        self.export_repo_var = tk.StringVar(value=str(cwd))
        self.export_output_var = tk.StringVar(value=str(cwd))
        self.import_file_var = tk.StringVar()
        self.import_output_var = tk.StringVar(value=str(cwd / 'restored_repo'))
        self.status_var = tk.StringVar(value='Ready')
        self.preview_var = tk.StringVar()
        self.stats_vars = {
            'files': tk.StringVar(value='0'),
            'text_files': tk.StringVar(value='0'),
            'binary_files': tk.StringVar(value='0'),
            'bytes': tk.StringVar(value='0 B'),
            'errors': tk.StringVar(value='0'),
        }

        self._build_styles()
        self._build_ui()
        self._bind_traces()
        self.update_export_preview()
        self.root.after(100, self.drain_events)

    def _build_styles(self):
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure(
            'Repo.Horizontal.TProgressbar',
            troughcolor=COLORS['surface'],
            background=COLORS['accent'],
            bordercolor=COLORS['border'],
            lightcolor=COLORS['accent'],
            darkcolor=COLORS['accent'],
        )

    def _build_ui(self):
        shell = tk.Frame(self.root, bg=COLORS['bg'])
        shell.pack(fill='both', expand=True, padx=24, pady=22)

        header = tk.Frame(shell, bg=COLORS['bg'])
        header.pack(fill='x')

        title_block = tk.Frame(header, bg=COLORS['bg'])
        title_block.pack(side='left', fill='x', expand=True)
        tk.Label(
            title_block,
            text='RepoBundle',
            font=('Inter', 24, 'bold'),
            fg=COLORS['text'],
            bg=COLORS['bg'],
        ).pack(anchor='w')
        tk.Label(
            title_block,
            text='Export and restore repositories as a single readable text bundle.',
            font=('Inter', 12),
            fg=COLORS['muted'],
            bg=COLORS['bg'],
        ).pack(anchor='w', pady=(4, 0))

        tabs = tk.Frame(header, bg=COLORS['surface'], highlightthickness=1, highlightbackground=COLORS['border'])
        tabs.pack(side='right', padx=(18, 0))
        self.export_tab = self._button(tabs, 'Export', lambda: self.set_mode('export'), width=10)
        self.export_tab.pack(side='left', padx=3, pady=3)
        self.import_tab = self._button(tabs, 'Import', lambda: self.set_mode('import'), width=10)
        self.import_tab.pack(side='left', padx=3, pady=3)

        main = tk.Frame(shell, bg=COLORS['bg'])
        main.pack(fill='both', expand=True, pady=(22, 0))

        self.forms = tk.Frame(main, bg=COLORS['surface'], highlightthickness=1, highlightbackground=COLORS['border'])
        self.forms.pack(fill='x')

        self.export_frame = tk.Frame(self.forms, bg=COLORS['surface'])
        self.import_frame = tk.Frame(self.forms, bg=COLORS['surface'])
        self._build_export_form(self.export_frame)
        self._build_import_form(self.import_frame)

        stats = tk.Frame(main, bg=COLORS['bg'])
        stats.pack(fill='x', pady=(16, 0))
        self._stat_card(stats, 'Files', self.stats_vars['files']).pack(side='left', fill='x', expand=True, padx=(0, 8))
        self._stat_card(stats, 'Text', self.stats_vars['text_files']).pack(side='left', fill='x', expand=True, padx=8)
        self._stat_card(stats, 'Binary', self.stats_vars['binary_files']).pack(side='left', fill='x', expand=True, padx=8)
        self._stat_card(stats, 'Size', self.stats_vars['bytes']).pack(side='left', fill='x', expand=True, padx=8)
        self._stat_card(stats, 'Errors', self.stats_vars['errors'], COLORS['danger']).pack(side='left', fill='x', expand=True, padx=(8, 0))

        log_panel = tk.Frame(main, bg=COLORS['surface'], highlightthickness=1, highlightbackground=COLORS['border'])
        log_panel.pack(fill='both', expand=True, pady=(16, 0))
        tk.Label(
            log_panel,
            text='Activity',
            font=('Inter', 12, 'bold'),
            fg=COLORS['text'],
            bg=COLORS['surface'],
        ).pack(anchor='w', padx=18, pady=(16, 8))

        log_body = tk.Frame(log_panel, bg=COLORS['entry'], highlightthickness=1, highlightbackground=COLORS['border'])
        log_body.pack(fill='both', expand=True, padx=18, pady=(0, 18))
        self.log_text = tk.Text(
            log_body,
            bg=COLORS['entry'],
            fg=COLORS['text'],
            insertbackground=COLORS['text'],
            relief='flat',
            wrap='word',
            height=10,
            padx=12,
            pady=10,
            font=('Menlo', 11),
            state='disabled',
        )
        scrollbar = tk.Scrollbar(log_body, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        footer = tk.Frame(shell, bg=COLORS['bg'])
        footer.pack(fill='x', pady=(14, 0))
        self.progress = ttk.Progressbar(footer, mode='indeterminate', style='Repo.Horizontal.TProgressbar')
        self.progress.pack(side='left', fill='x', expand=True)
        tk.Label(
            footer,
            textvariable=self.status_var,
            font=('Inter', 11),
            fg=COLORS['muted'],
            bg=COLORS['bg'],
            width=28,
            anchor='e',
        ).pack(side='right', padx=(16, 0))

        self.set_mode('export')

    def _build_export_form(self, parent):
        self._form_title(parent, 'Export Repository', 'Create a timestamped bundle from a local repository.')
        self._field(parent, 'Repository', self.export_repo_var, self.choose_export_repo)
        self._field(parent, 'Save to', self.export_output_var, self.choose_export_output)
        tk.Label(
            parent,
            textvariable=self.preview_var,
            font=('Inter', 11),
            fg=COLORS['muted'],
            bg=COLORS['surface'],
        ).pack(anchor='w', padx=18, pady=(0, 16))

        actions = tk.Frame(parent, bg=COLORS['surface'])
        actions.pack(fill='x', padx=18, pady=(0, 18))
        self.export_button = self._button(actions, 'Export Bundle', self.run_export, primary=True)
        self.export_button.pack(side='left')
        self.open_export_button = self._button(actions, 'Open Output', self.open_last_export)
        self.open_export_button.pack(side='left', padx=(10, 0))
        self.open_export_button.configure(state='disabled')
        self.controls.extend([self.export_button, self.open_export_button])

    def _build_import_form(self, parent):
        self._form_title(parent, 'Import Bundle', 'Restore files and folders from a RepoBundle export.')
        self._field(parent, 'Bundle file', self.import_file_var, self.choose_import_file)
        self._field(parent, 'Restore to', self.import_output_var, self.choose_import_output)

        actions = tk.Frame(parent, bg=COLORS['surface'])
        actions.pack(fill='x', padx=18, pady=(0, 18))
        self.import_button = self._button(actions, 'Import Bundle', self.run_import, primary=True)
        self.import_button.pack(side='left')
        self.open_restore_button = self._button(actions, 'Open Folder', self.open_last_restore)
        self.open_restore_button.pack(side='left', padx=(10, 0))
        self.open_restore_button.configure(state='disabled')
        self.controls.extend([self.import_button, self.open_restore_button])

    def _form_title(self, parent, title, subtitle):
        tk.Label(
            parent,
            text=title,
            font=('Inter', 16, 'bold'),
            fg=COLORS['text'],
            bg=COLORS['surface'],
        ).pack(anchor='w', padx=18, pady=(18, 3))
        tk.Label(
            parent,
            text=subtitle,
            font=('Inter', 11),
            fg=COLORS['muted'],
            bg=COLORS['surface'],
        ).pack(anchor='w', padx=18, pady=(0, 16))

    def _field(self, parent, label, variable, command):
        row = tk.Frame(parent, bg=COLORS['surface'])
        row.pack(fill='x', padx=18, pady=(0, 12))
        tk.Label(
            row,
            text=label,
            font=('Inter', 11, 'bold'),
            fg=COLORS['muted'],
            bg=COLORS['surface'],
            width=12,
            anchor='w',
        ).pack(side='left')

        entry = tk.Entry(
            row,
            textvariable=variable,
            bg=COLORS['entry'],
            fg=COLORS['text'],
            insertbackground=COLORS['text'],
            relief='flat',
            highlightthickness=1,
            highlightbackground=COLORS['border'],
            highlightcolor=COLORS['info'],
            font=('Inter', 12),
        )
        entry.pack(side='left', fill='x', expand=True, ipady=8)
        browse = self._button(row, 'Browse', command)
        browse.pack(side='left', padx=(10, 0))
        self.controls.extend([entry, browse])

    def _stat_card(self, parent, label, value_var, value_color=None):
        card = tk.Frame(parent, bg=COLORS['surface'], highlightthickness=1, highlightbackground=COLORS['border'])
        tk.Label(card, text=label, font=('Inter', 10, 'bold'), fg=COLORS['dim'], bg=COLORS['surface']).pack(
            anchor='w',
            padx=14,
            pady=(12, 1),
        )
        tk.Label(
            card,
            textvariable=value_var,
            font=('Inter', 15, 'bold'),
            fg=value_color or COLORS['text'],
            bg=COLORS['surface'],
        ).pack(anchor='w', padx=14, pady=(0, 12))
        return card

    def _button(self, parent, text, command, primary=False, width=None):
        button = tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            bg=COLORS['text'] if primary else COLORS['surface_alt'],
            fg=COLORS['bg'] if primary else COLORS['text'],
            activebackground=COLORS['accent'] if primary else COLORS['border'],
            activeforeground=COLORS['bg'] if primary else COLORS['text'],
            disabledforeground=COLORS['dim'],
            relief='flat',
            borderwidth=0,
            padx=14,
            pady=9,
            font=('Inter', 11, 'bold'),
            cursor='hand2',
        )
        return button

    def _bind_traces(self):
        self.export_repo_var.trace('w', lambda *_: self.update_export_preview())
        self.export_output_var.trace('w', lambda *_: self.update_export_preview())

    def set_mode(self, mode):
        if self.busy:
            return
        self.mode = mode
        self.export_frame.pack_forget()
        self.import_frame.pack_forget()
        if mode == 'export':
            self.export_frame.pack(fill='x')
        else:
            self.import_frame.pack(fill='x')
        self.export_tab.configure(bg=COLORS['accent'] if mode == 'export' else COLORS['surface_alt'])
        self.import_tab.configure(bg=COLORS['accent'] if mode == 'import' else COLORS['surface_alt'])

    def choose_export_repo(self):
        selected = filedialog.askdirectory(initialdir=self.export_repo_var.get() or str(Path.cwd()))
        if selected:
            self.export_repo_var.set(selected)

    def choose_export_output(self):
        selected = filedialog.askdirectory(initialdir=self.export_output_var.get() or str(Path.cwd()))
        if selected:
            self.export_output_var.set(selected)

    def choose_import_file(self):
        selected = filedialog.askopenfilename(
            initialdir=str(Path.cwd()),
            filetypes=[('RepoBundle exports', '*.txt'), ('All files', '*.*')],
        )
        if selected:
            self.import_file_var.set(selected)

    def choose_import_output(self):
        selected = filedialog.askdirectory(initialdir=self.import_output_var.get() or str(Path.cwd()))
        if selected:
            self.import_output_var.set(selected)

    def update_export_preview(self):
        repo = self.export_repo_var.get().strip()
        output_dir = self.export_output_var.get().strip()
        if repo and output_dir:
            try:
                preview = default_output_path(repo, output_dir)
                self.preview_var.set(f"Output file: {preview.name}")
            except Exception:
                self.preview_var.set('Output file: select a valid repository and destination')
        else:
            self.preview_var.set('Output file: select a repository and destination')

    def run_export(self):
        repo_value = self.export_repo_var.get().strip()
        output_value = self.export_output_var.get().strip()
        if not repo_value or not output_value:
            messagebox.showerror('RepoBundle', 'Choose a repository folder and output folder.')
            return

        repo = Path(repo_value).expanduser()
        output_dir = Path(output_value).expanduser()
        if not repo.is_dir():
            messagebox.showerror('RepoBundle', 'Choose a valid repository folder.')
            return
        if not output_dir.exists() or not output_dir.is_dir():
            messagebox.showerror('RepoBundle', 'Choose a valid output folder.')
            return

        output_path = default_output_path(repo, output_dir)
        self.clear_log()
        self.reset_stats()
        self.set_busy(True, 'Exporting...')
        self.last_export_path = None
        self.open_export_button.configure(state='disabled')

        thread = threading.Thread(
            target=self._export_worker,
            args=(repo, output_path),
            daemon=True,
        )
        thread.start()

    def _export_worker(self, repo, output_path):
        try:
            summary = export_repository(
                repo,
                output_path,
                log=lambda message: self.events.put(('log', message)),
                progress=lambda summary: self.events.put(('progress', summary)),
            )
            self.events.put(('export_done', summary))
        except Exception as exc:
            self.events.put(('error', str(exc)))

    def run_import(self):
        file_value = self.import_file_var.get().strip()
        output_value = self.import_output_var.get().strip()
        if not file_value or not output_value:
            messagebox.showerror('RepoBundle', 'Choose an export file and restore folder.')
            return

        export_file = Path(file_value).expanduser()
        output_dir = Path(output_value).expanduser()
        if not export_file.is_file():
            messagebox.showerror('RepoBundle', 'Choose a valid RepoBundle export file.')
            return
        if not output_dir.parent.exists():
            messagebox.showerror('RepoBundle', 'Choose a restore location with an existing parent folder.')
            return

        self.clear_log()
        self.reset_stats()
        self.set_busy(True, 'Importing...')
        self.last_restore_dir = None
        self.open_restore_button.configure(state='disabled')

        thread = threading.Thread(
            target=self._import_worker,
            args=(export_file, output_dir),
            daemon=True,
        )
        thread.start()

    def _import_worker(self, export_file, output_dir):
        try:
            summary = restore_repository(
                export_file,
                output_dir,
                log=lambda message: self.events.put(('log', message)),
                progress=lambda summary: self.events.put(('progress', summary)),
            )
            self.events.put(('import_done', summary))
        except Exception as exc:
            self.events.put(('error', str(exc)))

    def drain_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == 'log':
                    self.append_log(payload)
                elif kind == 'progress':
                    self.update_stats(payload)
                elif kind == 'export_done':
                    self.finish_export(payload)
                elif kind == 'import_done':
                    self.finish_import(payload)
                elif kind == 'error':
                    self.finish_error(payload)
        except queue.Empty:
            pass
        self.root.after(100, self.drain_events)

    def finish_export(self, summary):
        self.update_stats(summary)
        self.last_export_path = Path(summary['output_path'])
        self.open_export_button.configure(state='normal')
        self.set_busy(False, f"Exported {summary['files']} files")

    def finish_import(self, summary):
        self.update_stats(summary)
        self.last_restore_dir = Path(summary['output_path'])
        self.open_restore_button.configure(state='normal')
        self.set_busy(False, f"Imported {summary['files']} files")

    def finish_error(self, message):
        self.append_log(f"Error: {message}")
        self.set_busy(False, 'Error')
        messagebox.showerror('RepoBundle', message)

    def set_busy(self, busy, status):
        self.busy = busy
        self.status_var.set(status)
        if busy:
            self.progress.start(10)
        else:
            self.progress.stop()
        for control in self.controls:
            if control in (self.open_export_button, self.open_restore_button):
                continue
            control.configure(state='disabled' if busy else 'normal')
        if busy:
            self.open_export_button.configure(state='disabled')
            self.open_restore_button.configure(state='disabled')
        else:
            export_ready = self.last_export_path is not None and self.last_export_path.exists()
            restore_ready = self.last_restore_dir is not None and self.last_restore_dir.exists()
            self.open_export_button.configure(state='normal' if export_ready else 'disabled')
            self.open_restore_button.configure(state='normal' if restore_ready else 'disabled')

    def reset_stats(self):
        for key, var in self.stats_vars.items():
            var.set('0 B' if key == 'bytes' else '0')

    def update_stats(self, summary):
        self.stats_vars['files'].set(str(summary.get('files', 0)))
        self.stats_vars['text_files'].set(str(summary.get('text_files', 0)))
        self.stats_vars['binary_files'].set(str(summary.get('binary_files', 0)))
        self.stats_vars['bytes'].set(format_bytes(summary.get('bytes', 0)))
        self.stats_vars['errors'].set(str(summary.get('errors', 0)))

    def append_log(self, message):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', f"{message}\n")
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def clear_log(self):
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

    def open_last_export(self):
        if not self.last_export_path or not self.last_export_path.exists():
            messagebox.showerror('RepoBundle', 'No exported file is available yet.')
            return
        try:
            open_path(self.last_export_path)
        except Exception as exc:
            messagebox.showerror('RepoBundle', f"Could not open exported file: {exc}")

    def open_last_restore(self):
        if not self.last_restore_dir or not self.last_restore_dir.exists():
            messagebox.showerror('RepoBundle', 'No restored folder is available yet.')
            return
        try:
            open_path(self.last_restore_dir)
        except Exception as exc:
            messagebox.showerror('RepoBundle', f"Could not open restored folder: {exc}")


def main():
    root = tk.Tk()
    RepoBundleApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
