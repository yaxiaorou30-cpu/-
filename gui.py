#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI+舆情检测系统 - GUI 图形界面
支持地区三级选择、采集阈值等级、热度分析
"""
import os
import sys
import threading
import time
from datetime import datetime
from tkinter import *
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.orchestrator import generate_report
from src.template_manager import TemplateManager
from src.crawler import crawl_and_save, crawl_video_and_save, TIME_RANGE_MAP, PLATFORM_LIST, COLLECT_LEVELS
from src.heat_analyzer import HeatAnalyzer, get_all_provinces, get_cities_by_province, build_region_text
from src.file_namer import generate_filename, ensure_unique_path
from src.system_auth import (
    DEFAULT_ABSOLUTE_TIMEOUT_SECONDS,
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    SYSTEM_ROLE,
    SystemAccountStore,
)


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SYSTEM_USER_STORE_FILE = os.path.join(PROJECT_ROOT, "data", "system_users.secure.json")


def prompt_system_login(root, account_store, reason=""):
    """显示本机系统账号登录框；取消时返回 None。"""
    if not account_store.has_users() or not account_store.has_enabled_users():
        messagebox.showerror(
            "尚未配置系统账号",
            "请先运行“启动.bat”，在网页首次设置中创建本机唯一账号并保存恢复码。",
            parent=root,
        )
        return None

    result = {"username": None}
    dialog = Toplevel(root)
    dialog.title("系统账号登录")
    dialog.geometry("390x300")
    dialog.resizable(False, False)
    dialog.grab_set()

    body = Frame(dialog, padx=28, pady=24)
    body.pack(fill=BOTH, expand=True)
    Label(body, text="AI+舆情检测系统", font=("微软雅黑", 16, "bold")).pack(anchor=W)
    Label(
        body,
        text=reason or "仅限已配置的民警用户登录",
        font=("微软雅黑", 9),
        fg="#667085",
        wraplength=330,
        justify=LEFT,
    ).pack(anchor=W, pady=(5, 16))

    username_var = StringVar()
    password_var = StringVar()
    error_var = StringVar()
    Label(body, text="系统账号", font=("微软雅黑", 9, "bold")).pack(anchor=W)
    username_entry = Entry(body, textvariable=username_var, font=("微软雅黑", 10))
    username_entry.pack(fill=X, pady=(4, 10))
    Label(body, text="密码", font=("微软雅黑", 9, "bold")).pack(anchor=W)
    password_entry = Entry(body, textvariable=password_var, show="*", font=("微软雅黑", 10))
    password_entry.pack(fill=X, pady=(4, 5))
    Label(body, textvariable=error_var, font=("微软雅黑", 9), fg="#b42318").pack(anchor=W)

    def submit(event=None):
        auth = account_store.authenticate(username_var.get(), password_var.get())
        password_var.set("")
        if not auth.ok:
            error_var.set("账号或密码错误，或账号已停用")
            password_entry.focus_set()
            return
        result["username"] = auth.username
        dialog.destroy()

    def cancel():
        dialog.destroy()

    Button(
        body,
        text="登录",
        command=submit,
        font=("微软雅黑", 10, "bold"),
        bg="#0f766e",
        fg="white",
        width=12,
    ).pack(pady=(10, 0))
    dialog.bind("<Return>", submit)
    dialog.protocol("WM_DELETE_WINDOW", cancel)
    username_entry.focus_set()
    dialog.lift()
    root.wait_window(dialog)
    return result["username"]


class GUIApp:
    def __init__(self, root, account_store, current_username):
        self.root = root
        self.root.title("AI+舆情检测系统")
        self.root.geometry("950x750")
        self.root.resizable(True, True)

        self.font_title = ("微软雅黑", 16, "bold")
        self.font_normal = ("微软雅黑", 10)
        self.font_small = ("微软雅黑", 9)
        self.font_btn = ("微软雅黑", 11, "bold")

        self.selected_platforms = PLATFORM_LIST.copy()
        self.account_info = {}
        self.heat_analyzer = HeatAnalyzer()
        self.system_account_store = account_store
        self.current_username = current_username
        self.last_activity_monotonic = time.monotonic()
        self.session_started_monotonic = self.last_activity_monotonic
        self.auth_dialog_active = False

        self.setup_ui()
        self.root.bind_all("<Any-KeyPress>", self._record_activity, add="+")
        self.root.bind_all("<Any-Button>", self._record_activity, add="+")
        self.root.after(1000, self._check_system_session)

    def setup_ui(self):
        main_frame = Frame(self.root, padx=20, pady=15)
        main_frame.pack(fill=BOTH, expand=True)

        session_frame = Frame(main_frame)
        session_frame.pack(fill=X, pady=(0, 4))
        self.system_user_var = StringVar(value=f"{self.current_username} · {SYSTEM_ROLE}")
        Label(
            session_frame,
            textvariable=self.system_user_var,
            font=self.font_small,
            fg="#344054",
        ).pack(side=LEFT)
        Button(
            session_frame,
            text="退出系统",
            command=self.logout_system,
            font=self.font_small,
            width=8,
        ).pack(side=RIGHT)

        # 标题
        Label(main_frame, text="AI+舆情检测系统", font=self.font_title, fg="#2c3e50").pack(pady=(0, 10))

        # ===== 采集设置区域 =====
        settings_frame = LabelFrame(main_frame, text="采集设置", font=self.font_normal, padx=10, pady=8)
        settings_frame.pack(fill=X, pady=(0, 8))

        # 第一行：采集模式 + 时间范围 + 采集等级
        row1 = Frame(settings_frame)
        row1.pack(fill=X, pady=4)

        Label(row1, text="采集模式：", font=self.font_small).pack(side=LEFT)
        self.crawl_mode_var = StringVar(value="keyword")
        Radiobutton(row1, text="关键词", variable=self.crawl_mode_var, value="keyword",
                   font=self.font_small, command=self.on_crawl_mode_changed).pack(side=LEFT, padx=5)
        Radiobutton(row1, text="视频定向", variable=self.crawl_mode_var, value="video",
                   font=self.font_small, command=self.on_crawl_mode_changed).pack(side=LEFT, padx=5)

        Label(row1, text="  时间：", font=self.font_small).pack(side=LEFT)
        self.time_var = StringVar(value="近一周")
        ttk.Combobox(row1, textvariable=self.time_var, values=list(TIME_RANGE_MAP.keys()),
                     state="readonly", width=10, font=self.font_small).pack(side=LEFT, padx=3)
        self.time_var.trace("w", self.on_time_changed)

        Label(row1, text="  采集等级：", font=self.font_small).pack(side=LEFT)
        self.collect_level_var = StringVar(value="标准采集")
        ttk.Combobox(row1, textvariable=self.collect_level_var, values=list(COLLECT_LEVELS.keys()),
                     state="readonly", width=10, font=self.font_small).pack(side=LEFT, padx=3)

        # 自定义时间行（默认隐藏）
        self.custom_time_frame = Frame(settings_frame)
        Label(self.custom_time_frame, text="自定义时间：", font=self.font_small).pack(side=LEFT)
        self.custom_start_var = StringVar()
        self.custom_end_var = StringVar()
        Entry(self.custom_time_frame, textvariable=self.custom_start_var, width=10,
              font=self.font_small).pack(side=LEFT, padx=3)
        Label(self.custom_time_frame, text="至", font=self.font_small).pack(side=LEFT)
        Entry(self.custom_time_frame, textvariable=self.custom_end_var, width=10,
              font=self.font_small).pack(side=LEFT, padx=3)
        Label(self.custom_time_frame, text="(YYYY-MM-DD)", font=self.font_small, fg="#95a5a6").pack(side=LEFT)

        # 关键词输入行（关键词模式）
        self.keywords_row = Frame(settings_frame)
        self.keywords_row.pack(fill=X, pady=4)
        Label(self.keywords_row, text="关键词：", font=self.font_small).pack(side=LEFT)
        self.keywords_var = StringVar(value="警情通报, 警方通报, 案件通报, 突发事件, 社会热点")
        Entry(self.keywords_row, textvariable=self.keywords_var, width=45, font=self.font_small).pack(side=LEFT, padx=3)
        Label(self.keywords_row, text="(逗号分隔)", font=self.font_small, fg="#95a5a6").pack(side=LEFT)

        # 第二行：地区三级选择
        self.region_frame = Frame(settings_frame)
        self.region_frame.pack(fill=X, pady=4)

        Label(self.region_frame, text="地区：", font=self.font_small).pack(side=LEFT)

        # 省份下拉
        self.province_var = StringVar(value="全国")
        provinces = ["全国"] + get_all_provinces()
        self.province_combo = ttk.Combobox(self.region_frame, textvariable=self.province_var,
                                            values=provinces, state="readonly", width=14, font=self.font_small)
        self.province_combo.pack(side=LEFT, padx=3)
        self.province_combo.bind("<<ComboboxSelected>>", self.on_province_changed)

        # 市下拉
        Label(self.region_frame, text="  市：", font=self.font_small).pack(side=LEFT)
        self.city_var = StringVar(value="")
        self.city_combo = ttk.Combobox(self.region_frame, textvariable=self.city_var,
                                        values=[], state="readonly", width=12, font=self.font_small)
        self.city_combo.pack(side=LEFT, padx=3)
        self.city_combo.bind("<<ComboboxSelected>>", self.on_city_changed)

        # 区/县输入（可选）
        Label(self.region_frame, text="  区/县：", font=self.font_small).pack(side=LEFT)
        self.district_var = StringVar()
        Entry(self.region_frame, textvariable=self.district_var, width=8, font=self.font_small).pack(side=LEFT, padx=3)

        # 视频链接行（默认隐藏）
        self.video_row = Frame(settings_frame)
        Label(self.video_row, text="视频链接：", font=self.font_small).pack(side=LEFT)
        self.video_url_var = StringVar()
        Entry(self.video_row, textvariable=self.video_url_var, width=50, font=self.font_small).pack(side=LEFT, padx=3)
        Label(self.video_row, text="(B站/抖音/快手)", font=self.font_small, fg="#95a5a6").pack(side=LEFT)

        # 第三行：社交增强平台选择
        row3 = Frame(settings_frame)
        row3.pack(fill=X, pady=4)

        Label(row3, text="社交增强：", font=self.font_small).pack(side=LEFT)
        Button(row3, text="全选", command=self.select_all_platforms,
               font=self.font_small, width=4).pack(side=LEFT, padx=5)
        Button(row3, text="取消", command=self.deselect_all_platforms,
               font=self.font_small, width=4).pack(side=LEFT)

        platform_frame = Frame(settings_frame)
        platform_frame.pack(fill=X, pady=2)

        cols = 5
        for i, platform in enumerate(PLATFORM_LIST):
            var = BooleanVar(value=True)
            Checkbutton(platform_frame, text=platform, variable=var, font=self.font_small,
                        command=lambda p=platform, v=var: self.on_platform_toggle(p, v)).grid(
                            row=i // cols, column=i % cols, sticky=W, padx=6)
            self.account_info[platform] = {"var": var}

        # ===== 操作按钮区域 =====
        btn_frame = Frame(main_frame)
        btn_frame.pack(fill=X, pady=10)

        self.action_btn = Button(
            btn_frame, text="一键采集并生成报告", command=self.start_full_process,
            font=self.font_btn, bg="#27ae60", fg="white", width=18, height=2
        )
        self.action_btn.pack(side=LEFT, padx=10)

        Button(btn_frame, text="仅采集", command=self.start_crawl_only,
               font=self.font_normal, width=8, height=2).pack(side=LEFT, padx=8)

        Button(btn_frame, text="仅生成", command=self.start_generate_only,
               font=self.font_normal, width=8, height=2).pack(side=LEFT, padx=8)

        Button(btn_frame, text="设置账号", command=self.show_account_dialog,
               font=self.font_small, width=7).pack(side=LEFT, padx=8)

        # ===== 热度分析区域 =====
        heat_frame = LabelFrame(main_frame, text="热度分析", font=self.font_normal, padx=10, pady=8)
        heat_frame.pack(fill=X, pady=(0, 8))

        self.heat_text = Text(heat_frame, height=5, width=80, font=self.font_small,
                             bg="#f5f5f5", relief=SUNKEN, state=DISABLED)
        self.heat_text.pack(fill=X)

        # ===== 执行日志区域 =====
        log_frame = LabelFrame(main_frame, text="执行日志", font=self.font_normal, padx=10, pady=8)
        log_frame.pack(fill=BOTH, expand=True)

        self.log_text = Text(log_frame, height=12, width=80, font=self.font_small,
                            bg="#f8f9fa", relief=SUNKEN, state=DISABLED)
        self.log_text.pack(fill=BOTH, expand=True)

        Scrollbar(log_frame, command=self.log_text.yview).pack(side=RIGHT, fill=Y)
        self.log_text.config(yscrollcommand=log_frame.children[list(log_frame.children.keys())[-1]].set)

        # 状态栏
        self.status_var = StringVar(value="就绪")
        Label(main_frame, textvariable=self.status_var, font=self.font_small,
              fg="#7f8c8d", anchor=W).pack(fill=X, pady=(5, 0))

    def on_crawl_mode_changed(self):
        mode = self.crawl_mode_var.get()
        if mode == "video":
            self.video_row.pack(fill=X, pady=4, before=self.region_frame)
            self.keywords_row.pack_forget()
            self.region_frame.pack_forget()
        else:
            self.video_row.pack_forget()
            self.keywords_row.pack(fill=X, pady=4, before=self.region_frame)
            self.region_frame.pack(fill=X, pady=4)

    def on_time_changed(self, *args):
        if self.time_var.get() == "自定义":
            self.custom_time_frame.pack(fill=X, pady=4)
        else:
            self.custom_time_frame.pack_forget()

    def on_province_changed(self, event=None):
        province = self.province_var.get()
        if province == "全国":
            self.city_combo["values"] = []
            self.city_var.set("")
        else:
            cities = ["全省"] + get_cities_by_province(province)
            self.city_combo["values"] = cities
            self.city_var.set("全省")

    def on_city_changed(self, event=None):
        pass  # 可扩展区县联动

    def get_region_text(self) -> str:
        """获取完整的地区文本"""
        province = self.province_var.get()
        city = self.city_var.get()
        district = self.district_var.get()

        if province == "全国":
            return None

        if city == "全省" or not city:
            return province

        if district:
            return f"{province}{city}{district}"

        return f"{province}{city}"

    def on_platform_toggle(self, platform, var):
        if var.get():
            if platform not in self.selected_platforms:
                self.selected_platforms.append(platform)
        else:
            if platform in self.selected_platforms:
                self.selected_platforms.remove(platform)

    def select_all_platforms(self):
        self.selected_platforms = PLATFORM_LIST.copy()
        for platform in PLATFORM_LIST:
            self.account_info[platform]["var"].set(True)

    def deselect_all_platforms(self):
        self.selected_platforms = []
        for platform in PLATFORM_LIST:
            self.account_info[platform]["var"].set(False)

    def show_account_dialog(self):
        if not self.ensure_active_session():
            return
        dialog = Toplevel(self.root)
        dialog.title("设置平台账号")
        dialog.geometry("450x350")
        dialog.transient(self.root)
        dialog.grab_set()

        Label(dialog, text="平台账号设置（仅内存存储）", font=self.font_title).pack(pady=10)

        scroll_frame = Frame(dialog)
        scroll_frame.pack(fill=BOTH, expand=True, padx=15)

        platforms_to_show = self.selected_platforms[:6] or PLATFORM_LIST[:6]

        for platform in platforms_to_show:
            frame = Frame(scroll_frame, pady=5)
            frame.pack(fill=X)

            Label(frame, text=platform, font=self.font_small, width=8).pack(side=LEFT)
            Label(frame, text="账号：", font=self.font_small).pack(side=LEFT)
            username_var = StringVar()
            Entry(frame, textvariable=username_var, width=12, font=self.font_small).pack(side=LEFT, padx=3)
            Label(frame, text="密码：", font=self.font_small).pack(side=LEFT)
            password_var = StringVar()
            Entry(frame, textvariable=password_var, width=12, font=self.font_small, show="*").pack(side=LEFT)

            self.account_info[platform]["username_var"] = username_var
            self.account_info[platform]["password_var"] = password_var

        def save():
            for platform in platforms_to_show:
                if "username_var" in self.account_info[platform]:
                    self.account_info[platform]["username"] = self.account_info[platform]["username_var"].get()
                    self.account_info[platform]["password"] = self.account_info[platform]["password_var"].get()
            messagebox.showinfo("成功", "账号已保存")
            dialog.destroy()

        Button(dialog, text="保存", command=save, font=self.font_normal,
               bg="#27ae60", fg="white", width=10).pack(pady=10)

    def log(self, message):
        self.log_text.config(state=NORMAL)
        self.log_text.insert(END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(END)
        self.log_text.config(state=DISABLED)
        self.root.update_idletasks()

    def update_heat_display(self, heat_result: dict, quality_result: dict):
        """更新热度分析显示"""
        self.heat_text.config(state=NORMAL)
        self.heat_text.delete(1.0, END)

        text = f"热度指数: {heat_result['heat_index']} ({heat_result['heat_level']}) | "
        text += f"数据量: {heat_result['total_posts']}条 | "
        text += f"平台覆盖: {len(heat_result['platforms'])}个 | "
        text += f"时效性: {heat_result['timeliness']:.0%}\n"

        text += f"采集状态: {quality_result.get('status_label', '未检查')} | "
        if quality_result['issues']:
            text += f"问题: {', '.join(quality_result['issues'][:2])}"

        self.heat_text.insert(END, text)
        self.heat_text.config(state=DISABLED)

    def start_full_process(self):
        if not self.ensure_active_session():
            return
        self.action_btn.config(state=DISABLED, text="处理中...")
        self.status_var.set("正在采集...")
        threading.Thread(target=self.run_full_process, daemon=True).start()

    def run_full_process(self):
        try:
            # 第一步：采集
            self.log("=" * 50)
            self.log("开始采集数据...")

            time_range = self.time_var.get()
            collect_level = self.collect_level_var.get()
            crawl_mode = self.crawl_mode_var.get()
            if not self.selected_platforms:
                self.selected_platforms = PLATFORM_LIST

            accounts = {}
            for platform in self.selected_platforms:
                if self.account_info[platform].get("username"):
                    accounts[platform] = {
                        "username": self.account_info[platform]["username"],
                        "password": self.account_info[platform].get("password", "")
                    }

            region = self.get_region_text()
            self.log(f"采集等级: {collect_level}")
            self.log(f"时间范围: {time_range}")
            self.log(f"地区: {region or '全国'}")
            self.log(f"社交增强平台: {', '.join(self.selected_platforms)}")
            self.log(f"数据源策略: 稳定公开源优先")

            if crawl_mode == "video":
                video_url = self.video_url_var.get().strip()
                if not video_url:
                    messagebox.showwarning("警告", "请输入视频链接！")
                    self.action_btn.config(state=NORMAL, text="一键采集并生成报告")
                    return
                self.log(f"视频: {video_url}")
                input_file = crawl_video_and_save(
                    video_url=video_url,
                    social_platforms=self.selected_platforms,
                    time_range=time_range,
                    collect_level=collect_level,
                    accounts=accounts,
                    source_strategy="stable_first",
                )
            else:
                # 解析用户输入的关键词
                keywords_text = self.keywords_var.get().strip()
                if keywords_text:
                    keywords = [k.strip() for k in keywords_text.split(',') if k.strip()]
                else:
                    keywords = ["警情通报", "警方通报", "案件通报", "突发事件"]

                input_file = crawl_and_save(
                    keywords=keywords,
                    region=region,
                    time_range=time_range,
                    social_platforms=self.selected_platforms,
                    collect_level=collect_level,
                    accounts=accounts,
                    source_strategy="stable_first",
                )

            self.log(f"采集完成！数据: {input_file}")
            self.status_var.set("正在分析热度...")

            # 第二步：热度分析
            import json
            with open(input_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            meta_file = os.path.splitext(input_file)[0] + "_meta.json"
            if os.path.exists(meta_file):
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                summary = meta.get("summary", {})
                self.log(
                    f"真实数据: {summary.get('real_count', 0)} 条，"
                    f"稳定源: {summary.get('stable_real_count', 0)} 条，"
                    f"社交增强: {summary.get('social_real_count', 0)} 条，"
                    f"检查状态: {summary.get('check_status_label', '未检查')}"
                )
                if not meta.get("reached_min_real_results", True):
                    self.log("[提示] 真实数据未达到最低阈值，请调整关键词或检查网络/公开数据源。")

            heat_result = self.heat_analyzer.calculate_heat_index(data)
            quality_result = self.heat_analyzer.analyze_collection_quality(data)
            self.update_heat_display(heat_result, quality_result)

            self.log(f"热度指数: {heat_result['heat_index']} ({heat_result['heat_level']})")
            self.log(
                f"采集检查: {quality_result.get('status_label', '未检查')}，"
                f"{quality_result.get('status_detail', '')}"
            )

            self.status_var.set("正在生成报告...")

            # 第三步：生成报告
            self.log("-" * 50)
            self.log("开始生成报告...")

            os.makedirs("output", exist_ok=True)
            tm = TemplateManager("config/templates")
            templates = tm.list_templates()

            from src.analyzer import Analyzer
            from src.preprocessor import Preprocessor
            preprocessor = Preprocessor()
            analyzer = Analyzer()
            records = preprocessor.process(data)
            records = preprocessor.deduplicate(records)
            analysis_ctx = analyzer.analyze(records)
            event_keyword = analysis_ctx.event_keyword
            self.log(f"事件关键词: {event_keyword}")

            success_count = 0
            for template in templates:
                filename = generate_filename(
                    region=region,
                    time_range=time_range,
                    template_name=template["name"],
                    is_same_region_time=len(templates) > 1,
                    event_keyword=event_keyword,
                )
                output_path = ensure_unique_path("output", filename)

                self.log(f"生成: {template['name']}")
                try:
                    generate_report(input_json=input_file, template_id=template["id"], output_docx=output_path)
                    self.log(f"  ✓ {output_path}")
                    success_count += 1
                except Exception as e:
                    self.log(f"  ✗ 失败: {str(e)}")

            self.log("=" * 50)
            self.log(f"全部完成！成功生成 {success_count}/{len(templates)} 个报告")
            self.status_var.set("完成")
            messagebox.showinfo("完成", f"成功生成 {success_count} 个报告！")
            os.startfile("output")

        except Exception as e:
            self.log(f"[错误] {str(e)}")
            self.status_var.set("出错")
            messagebox.showerror("错误", f"处理出错：{str(e)}")

        finally:
            self.action_btn.config(state=NORMAL, text="一键采集并生成报告")
            for platform in PLATFORM_LIST:
                self.account_info[platform]["password"] = ""

    def start_crawl_only(self):
        if not self.ensure_active_session():
            return
        self.action_btn.config(state=DISABLED)
        self.status_var.set("正在采集...")
        threading.Thread(target=self.run_crawl_only, daemon=True).start()

    def run_crawl_only(self):
        try:
            time_range = self.time_var.get()
            collect_level = self.collect_level_var.get()
            crawl_mode = self.crawl_mode_var.get()

            if not self.selected_platforms:
                self.selected_platforms = PLATFORM_LIST

            region = self.get_region_text()
            self.log(f"开始采集... (等级: {collect_level})")
            self.log("数据源策略: 稳定公开源优先")

            if crawl_mode == "video":
                video_url = self.video_url_var.get().strip()
                if not video_url:
                    messagebox.showwarning("警告", "请输入视频链接！")
                    self.action_btn.config(state=NORMAL)
                    return
                input_file = crawl_video_and_save(video_url=video_url, social_platforms=self.selected_platforms,
                                                  time_range=time_range, collect_level=collect_level,
                                                  source_strategy="stable_first")
            else:
                # 解析用户输入的关键词
                keywords_text = self.keywords_var.get().strip()
                if keywords_text:
                    keywords = [k.strip() for k in keywords_text.split(',') if k.strip()]
                else:
                    keywords = ["警情通报", "警方通报", "案件通报"]
                input_file = crawl_and_save(keywords=keywords,
                                            region=region, time_range=time_range,
                                            social_platforms=self.selected_platforms, collect_level=collect_level,
                                            source_strategy="stable_first")

            self.log(f"采集完成！数据: {input_file}")

            # 显示热度分析
            import json
            with open(input_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            meta_file = os.path.splitext(input_file)[0] + "_meta.json"
            if os.path.exists(meta_file):
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                summary = meta.get("summary", {})
                self.log(
                    f"真实数据: {summary.get('real_count', 0)} 条，"
                    f"检查状态: {summary.get('check_status_label', '未检查')}"
                )
                if not meta.get("reached_min_real_results", True):
                    self.log("[提示] 真实数据未达到最低阈值，请调整关键词或检查网络/公开数据源。")

            heat_result = self.heat_analyzer.calculate_heat_index(data)
            quality_result = self.heat_analyzer.analyze_collection_quality(data)
            self.update_heat_display(heat_result, quality_result)

            self.status_var.set("采集完成")
            messagebox.showinfo("完成", "数据采集完成！")

        except Exception as e:
            self.log(f"[错误] {str(e)}")
            messagebox.showerror("错误", f"采集出错：{str(e)}")

        finally:
            self.action_btn.config(state=NORMAL)

    def start_generate_only(self):
        if not self.ensure_active_session():
            return
        self.action_btn.config(state=DISABLED)
        self.status_var.set("正在生成...")
        threading.Thread(target=self.run_generate_only, daemon=True).start()

    def run_generate_only(self):
        try:
            input_file = "data/latest_news.json"
            if not os.path.exists(input_file):
                input_file = "data/sample_input.json"

            self.log(f"开始生成报告... (输入: {input_file})")

            os.makedirs("output", exist_ok=True)
            tm = TemplateManager("config/templates")
            templates = tm.list_templates()
            region = self.get_region_text()

            import json
            with open(input_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            from src.analyzer import Analyzer
            from src.preprocessor import Preprocessor
            preprocessor = Preprocessor()
            analyzer = Analyzer()
            records = preprocessor.process(data)
            records = preprocessor.deduplicate(records)
            analysis_ctx = analyzer.analyze(records)
            event_keyword = analysis_ctx.event_keyword
            self.log(f"事件关键词: {event_keyword}")

            for template in templates:
                filename = generate_filename(region=region, time_range=self.time_var.get(),
                                          template_name=template["name"], is_same_region_time=len(templates) > 1,
                                          event_keyword=event_keyword)
                output_path = ensure_unique_path("output", filename)
                self.log(f"生成: {template['name']}")
                generate_report(input_json=input_file, template_id=template["id"], output_docx=output_path)
                self.log(f"  ✓ {output_path}")

            self.log("报告生成完成！")
            self.status_var.set("完成")
            messagebox.showinfo("完成", "报告生成完成！")
            os.startfile("output")

        except Exception as e:
            self.log(f"[错误] {str(e)}")
            messagebox.showerror("错误", f"生成出错：{str(e)}")

        finally:
            self.action_btn.config(state=NORMAL)

    def _record_activity(self, event=None):
        if self.current_username and not self.auth_dialog_active:
            self.last_activity_monotonic = time.monotonic()

    def _invalid_session_reason(self):
        if not self.current_username:
            return "请重新登录系统账号"
        if not self.system_account_store.is_enabled(self.current_username):
            return "当前系统账号已停用，请使用可用账号重新登录"
        if time.monotonic() - self.last_activity_monotonic >= DEFAULT_IDLE_TIMEOUT_SECONDS:
            return "长时间未操作，系统已锁定，请重新登录"
        if time.monotonic() - self.session_started_monotonic >= DEFAULT_ABSOLUTE_TIMEOUT_SECONDS:
            return "本次登录已到期，请重新登录"
        return ""

    def ensure_active_session(self):
        reason = self._invalid_session_reason()
        if reason:
            self._lock_for_reauthentication(reason)
        if self.current_username:
            self.last_activity_monotonic = time.monotonic()
        return bool(self.current_username)

    def _check_system_session(self):
        reason = self._invalid_session_reason()
        if reason:
            self._lock_for_reauthentication(reason)
        try:
            if self.root.winfo_exists():
                self.root.after(1000, self._check_system_session)
        except TclError:
            pass

    def _lock_for_reauthentication(self, reason):
        if self.auth_dialog_active:
            return
        self.auth_dialog_active = True
        self.current_username = None
        self.system_user_var.set("未登录")
        self.root.withdraw()
        try:
            username = prompt_system_login(self.root, self.system_account_store, reason)
            if not username:
                self.root.destroy()
                return
            self.current_username = username
            self.system_user_var.set(f"{username} · {SYSTEM_ROLE}")
            self.last_activity_monotonic = time.monotonic()
            self.session_started_monotonic = self.last_activity_monotonic
            self.root.deiconify()
            self.root.lift()
        finally:
            self.auth_dialog_active = False

    def logout_system(self):
        self._lock_for_reauthentication("已退出系统，请重新登录")


def main():
    root = Tk()
    root.withdraw()
    account_store = SystemAccountStore(SYSTEM_USER_STORE_FILE)
    username = prompt_system_login(root, account_store)
    if not username:
        root.destroy()
        return
    app = GUIApp(root, account_store, username)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
