"""Simple GUI wrapper around the Yahoo realtime scraper tools.

The goal is to provide a "one click" experience that a child could use to
extract the browser session details from a HAR file and collect `gofile`
links from Yahoo's realtime search results.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, Optional, Set

import requests
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from har_session_extractor import DEFAULT_PATTERN, extract_session_from_har
from scrape_gofile_links import YahooRealtimeClient, fetch_links


class FriendlyApp:
    """Tkinter application that exposes the scraper through large buttons."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("かんたんYahooリンクひろい")
        self.root.geometry("780x640")
        self.root.minsize(720, 600)

        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TButton", font=("Meiryo", 12, "bold"), padding=10)
        style.configure("TLabel", font=("Meiryo", 11))
        style.configure("Header.TLabel", font=("Meiryo", 13, "bold"))

        self.har_path: Optional[Path] = None
        self.headers: Dict[str, str] = {}
        self.cookie_string: str = ""
        self.collected_links: Set[str] = set()

        self._build_har_section()
        self._build_scrape_section()
        self._build_results_section()

    # ------------------------------------------------------------------
    # UI builders
    def _build_har_section(self) -> None:
        frame = ttk.LabelFrame(self.root, text="ステップ1：HARファイルをよみこむ", padding=15)
        frame.pack(fill=tk.X, padx=15, pady=(15, 10))

        ttk.Label(frame, text="まずはブラウザから保存した HAR ファイルをえらびましょう。", style="Header.TLabel").pack(
            anchor=tk.W
        )

        choose_btn = ttk.Button(frame, text="HARファイルをえらぶ", command=self._choose_har)
        choose_btn.pack(pady=10)

        self.har_label_var = tk.StringVar(value="まだファイルがえらばれていません")
        ttk.Label(frame, textvariable=self.har_label_var).pack(anchor=tk.W)

        self.extract_btn = ttk.Button(
            frame,
            text="ワンクリックでヘッダーとクッキーをつくる",
            command=self._extract_session,
            state=tk.DISABLED,
        )
        self.extract_btn.pack(pady=10)

        ttk.Label(frame, text="下の枠に作られた内容が表示されます。", foreground="#1a73e8").pack(anchor=tk.W)

    def _build_scrape_section(self) -> None:
        frame = ttk.LabelFrame(self.root, text="ステップ2：リンクをあつめる", padding=15)
        frame.pack(fill=tk.X, padx=15, pady=(0, 10))

        ttk.Label(frame, text="必要な項目だけ入力して「スタート！」を押すだけ。", style="Header.TLabel").pack(
            anchor=tk.W
        )

        form = ttk.Frame(frame)
        form.pack(fill=tk.X, pady=10)

        ttk.Label(form, text="キーワード：").grid(row=0, column=0, sticky=tk.W, padx=(0, 5), pady=5)
        self.query_var = tk.StringVar(value="gofile")
        ttk.Entry(form, textvariable=self.query_var, width=25).grid(row=0, column=1, sticky=tk.W)

        ttk.Label(form, text="ページ数：").grid(row=0, column=2, sticky=tk.W, padx=(15, 5))
        self.pages_var = tk.IntVar(value=5)
        ttk.Spinbox(form, from_=1, to=50, textvariable=self.pages_var, width=5).grid(
            row=0, column=3, sticky=tk.W
        )

        ttk.Label(form, text="1ページの件数：").grid(row=0, column=4, sticky=tk.W, padx=(15, 5))
        self.batch_var = tk.IntVar(value=20)
        ttk.Spinbox(form, from_=5, to=100, increment=5, textvariable=self.batch_var, width=5).grid(
            row=0, column=5, sticky=tk.W
        )

        ttk.Label(form, text="最新順レベル (rkf)：").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.relevance_var = tk.IntVar(value=3)
        ttk.Spinbox(form, from_=1, to=6, textvariable=self.relevance_var, width=5).grid(
            row=1, column=1, sticky=tk.W
        )

        ttk.Label(form, text="クッキー (必要なら編集OK)：").grid(
            row=1, column=2, sticky=tk.W, padx=(15, 5)
        )
        self.cookie_entry = ttk.Entry(form, width=40)
        self.cookie_entry.grid(row=1, column=3, columnspan=3, sticky=tk.W + tk.E)

        self.scrape_btn = ttk.Button(frame, text="スタート！", command=self._start_scrape)
        self.scrape_btn.pack(pady=(0, 5))

        self.status_var = tk.StringVar(value="準備中…")
        ttk.Label(frame, textvariable=self.status_var, foreground="#0b8043").pack(anchor=tk.W)

    def _build_results_section(self) -> None:
        frame = ttk.LabelFrame(self.root, text="つくったヘッダー／クッキー と 集めたリンク", padding=15)
        frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))

        container = ttk.Panedwindow(frame, orient=tk.VERTICAL)
        container.pack(fill=tk.BOTH, expand=True)

        header_frame = ttk.Labelframe(container, text="ヘッダー (JSON形式)")
        cookie_frame = ttk.Labelframe(container, text="クッキー")
        links_frame = ttk.Labelframe(container, text="リンク一覧")

        container.add(header_frame, weight=3)
        container.add(cookie_frame, weight=1)
        container.add(links_frame, weight=3)

        self.headers_text = tk.Text(header_frame, height=8, font=("Consolas", 11))
        self.headers_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.cookie_text = tk.Text(cookie_frame, height=4, font=("Consolas", 11))
        self.cookie_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.links_text = tk.Text(links_frame, height=12, font=("Consolas", 11))
        self.links_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        buttons_frame = ttk.Frame(frame)
        buttons_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(buttons_frame, text="リンクをファイルに保存", command=self._save_links).pack(
            side=tk.LEFT
        )

        ttk.Button(buttons_frame, text="すべてクリア", command=self._reset_all).pack(side=tk.RIGHT)

    # ------------------------------------------------------------------
    # Event handlers
    def _choose_har(self) -> None:
        initial_dir = str(self.har_path.parent) if self.har_path else ""
        path = filedialog.askopenfilename(
            title="HARファイルをえらんでください",
            filetypes=[("HARファイル", "*.har"), ("すべてのファイル", "*.*")],
            initialdir=initial_dir,
        )
        if not path:
            return
        self.har_path = Path(path)
        self.har_label_var.set(f"えらんだファイル：{self.har_path.name}")
        self.extract_btn.config(state=tk.NORMAL)
        self.status_var.set("HARが選ばれました。ワンクリックで抽出できます！")

    def _extract_session(self) -> None:
        if not self.har_path:
            messagebox.showinfo("HARがありません", "先にHARファイルをえらんでください。")
            return

        try:
            headers, cookie = extract_session_from_har(self.har_path, DEFAULT_PATTERN, 0)
        except ValueError as exc:
            messagebox.showerror("抽出に失敗しました", str(exc))
            return
        except Exception as exc:  # pragma: no cover - unexpected failures
            messagebox.showerror("抽出に失敗しました", f"予期しないエラー: {exc}")
            return

        self.headers = headers
        self.cookie_string = cookie
        self.headers_text.delete("1.0", tk.END)
        self.headers_text.insert(tk.END, json.dumps(headers, indent=2, ensure_ascii=False))
        self.cookie_text.delete("1.0", tk.END)
        self.cookie_text.insert(tk.END, cookie)
        self.cookie_entry.delete(0, tk.END)
        self.cookie_entry.insert(0, cookie)

        header_path = self.har_path.with_name(self.har_path.stem + "_headers.json")
        header_path.write_text(json.dumps(headers, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        cookie_path = self.har_path.with_name(self.har_path.stem + "_cookie.txt")
        cookie_path.write_text(cookie, encoding="utf-8")

        messagebox.showinfo(
            "できました！",
            "ヘッダーとクッキーを作成しました。\n"
            f"・{header_path.name}\n"
            f"・{cookie_path.name}\n"
            "このままステップ2に進めます。",
        )
        self.status_var.set("抽出が完了しました。ステップ2でリンクを集めましょう。")

    def _start_scrape(self) -> None:
        self.scrape_btn.config(state=tk.DISABLED)
        self.status_var.set("リンクを集めています…")
        threading.Thread(target=self._run_scrape, daemon=True).start()

    def _run_scrape(self) -> None:
        try:
            query = self.query_var.get().strip() or "gofile"
            pages = max(1, int(self.pages_var.get()))
            batch = max(1, int(self.batch_var.get()))
            relevance = max(1, int(self.relevance_var.get()))

            headers_text = self.headers_text.get("1.0", tk.END).strip()
            headers = json.loads(headers_text) if headers_text else self.headers

            cookie = self.cookie_entry.get().strip() or self.cookie_string

            session = requests.Session()
            if headers:
                session.headers.update(headers)

            client = YahooRealtimeClient(session)
            if cookie:
                client.update_from_cookie_string(cookie)

            links = fetch_links(client, query, pages, batch, relevance)
        except json.JSONDecodeError as exc:
            self._notify_error("ヘッダーが正しいJSONではありません。", exc)
            return
        except requests.HTTPError as exc:
            self._notify_error("Yahooからエラーが返されました。", exc)
            return
        except Exception as exc:  # pragma: no cover - defensive guard
            self._notify_error("リンクの取得中にエラーが発生しました。", exc)
            return

        sorted_links = sorted(links)

        def _apply() -> None:
            self.collected_links = links
            self.links_text.delete("1.0", tk.END)
            self.links_text.insert(tk.END, "\n".join(sorted_links))

            if sorted_links:
                self.status_var.set(f"{len(sorted_links)}件のリンクを見つけました！保存もできます。")
            else:
                self.status_var.set("リンクは見つかりませんでした。キーワードやページ数を変えてみてください。")
            self.scrape_btn.config(state=tk.NORMAL)

        self.root.after(0, _apply)

    def _notify_error(self, message: str, exc: Exception) -> None:
        def _show() -> None:
            messagebox.showerror("エラー", f"{message}\n\n詳細: {exc}")
            self.status_var.set("エラーが出ました。設定を確認してもう一度ためしてください。")
            self.scrape_btn.config(state=tk.NORMAL)

        self.root.after(0, _show)

    def _save_links(self) -> None:
        if not self.collected_links:
            messagebox.showinfo("保存できません", "まだリンクが集まっていません。先にステップ2を実行してください。")
            return

        file_path = filedialog.asksaveasfilename(
            title="リンクの保存先をえらんでください",
            defaultextension=".txt",
            filetypes=[("テキストファイル", "*.txt"), ("すべてのファイル", "*.*")],
            initialfile="gofile_links.txt",
        )
        if not file_path:
            return

        path = Path(file_path)
        path.write_text("\n".join(sorted(self.collected_links)) + "\n", encoding="utf-8")
        messagebox.showinfo("保存しました", f"{path.name} にリンクを保存しました。")

    def _reset_all(self) -> None:
        self.har_path = None
        self.headers = {}
        self.cookie_string = ""
        self.collected_links = set()
        self.har_label_var.set("まだファイルがえらばれていません")
        self.extract_btn.config(state=tk.DISABLED)
        self.headers_text.delete("1.0", tk.END)
        self.cookie_text.delete("1.0", tk.END)
        self.links_text.delete("1.0", tk.END)
        self.cookie_entry.delete(0, tk.END)
        self.query_var.set("gofile")
        self.pages_var.set(5)
        self.batch_var.set(20)
        self.relevance_var.set(3)
        self.status_var.set("準備中…")


def main() -> None:
    root = tk.Tk()
    FriendlyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
