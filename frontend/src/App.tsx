import { createContext, FormEvent, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ColumnDef, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import ReactECharts from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import {
  Activity,
  ArrowLeft,
  BedDouble,
  BookOpenCheck,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  ClipboardList,
  Download,
  FileCheck2,
  History,
  Eye,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Menu,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
  UploadCloud,
  Users,
  X,
} from "lucide-react";
import { Link, Navigate, NavLink, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { api, authApi, formatDate, formatNumber, runsApi, setCsrfToken, uploadDataset } from "./api";
import type { CapacityEntry, Dataset, Page, Run, Session } from "./types";

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

const AuthContext = createContext<{
  session: Session | null;
  setSession: (session: Session | null) => void;
}>({ session: null, setSession: () => undefined });

const STATUS: Record<string, { label: string; className: string }> = {
  draft: { label: "پیش‌نویس", className: "neutral" },
  queued: { label: "در صف", className: "queued" },
  running: { label: "در حال اجرا", className: "running" },
  succeeded: { label: "تکمیل‌شده", className: "success" },
  failed: { label: "ناموفق", className: "danger" },
  cancelled: { label: "لغوشده", className: "neutral" },
};

function StatusBadge({ status }: { status: string }) {
  const item = STATUS[status] ?? STATUS.neutral;
  return <span className={`status ${item.className}`}>{item.label}</span>;
}

function Loading({ label = "در حال بارگذاری" }: { label?: string }) {
  return <div className="loading"><LoaderCircle className="spin" size={22} />{label}</div>;
}

function EmptyState({ title, text, action }: { title: string; text: string; action?: ReactNode }) {
  return <div className="empty"><div className="empty-icon"><ClipboardList /></div><h3>{title}</h3><p>{text}</p>{action}</div>;
}

function LoginPage() {
  const { setSession } = useContext(AuthContext);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const mutation = useMutation({
    mutationFn: () => authApi.login(username, password),
    onSuccess: (value) => { setCsrfToken(value.csrf_token); setSession(value); },
    onError: (reason: Error) => setError(reason.message),
  });
  return <main className="login-page">
    <section className="login-intro">
      <div className="brand-mark"><BedDouble size={30} /></div>
      <p className="eyebrow">سامانه رسمی امور خوابگاه</p>
      <div className="trust-row"><span><ShieldCheck /> داده‌ها در دانشگاه می‌مانند</span><span><BookOpenCheck /> امتیازها توضیح‌پذیرند</span></div>
    </section>
    <section className="login-panel">
      <form className="auth-card" onSubmit={(event) => { event.preventDefault(); setError(""); mutation.mutate(); }}>
        <div><p className="eyebrow">ورود مدیر سامانه</p><h2>خوش آمدید</h2><p className="muted">برای مدیریت اجراهای تخصیص وارد شوید.</p></div>
        {error && <div className="alert danger"><CircleAlert size={18} />{error}</div>}
        <label>نام کاربری<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required /></label>
        <label>رمز عبور<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" minLength={8} required /></label>
        <button className="button primary" disabled={mutation.isPending}>{mutation.isPending ? <LoaderCircle className="spin" /> : <ShieldCheck />} ورود امن</button>
        <p className="security-note">نشست شما پس از ۳۰ دقیقه عدم فعالیت منقضی می‌شود.</p>
      </form>
    </section>
  </main>;
}

function PasswordChange() {
  const { session, setSession } = useContext(AuthContext);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const mutation = useMutation({
    mutationFn: () => authApi.password(currentPassword, newPassword),
    onSuccess: (value) => { setCsrfToken(value.csrf_token); setSession(value); },
    onError: (reason: Error) => setError(reason.message),
  });
  if (!session?.must_change_password) return null;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (newPassword !== confirm) return setError("تکرار رمز عبور با رمز جدید یکسان نیست.");
    mutation.mutate();
  };
  return <div className="modal-backdrop"><form className="modal" onSubmit={submit}>
    <div className="modal-icon"><ShieldCheck /></div><h2>تغییر رمز عبور اولیه</h2><p className="muted">برای ادامه، یک رمز عبور حداقل ۱۲ حرفی تعیین کنید.</p>
    {error && <div className="alert danger">{error}</div>}
    <label>رمز فعلی<input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} required /></label>
    <label>رمز جدید<input type="password" minLength={12} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required /></label>
    <label>تکرار رمز جدید<input type="password" minLength={12} value={confirm} onChange={(e) => setConfirm(e.target.value)} required /></label>
    <button className="button primary" disabled={mutation.isPending}>ثبت رمز و ادامه</button>
  </form></div>;
}

function Shell({ children }: { children: ReactNode }) {
  const { session, setSession } = useContext(AuthContext);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const logout = async () => { await authApi.logout(); setSession(null); navigate("/login"); };
  return <div className="app-shell">
    <aside className={open ? "sidebar open" : "sidebar"}>
      <div className="sidebar-brand"><span className="brand-mark small"><BedDouble /></span><span><strong>یونی‌میت</strong><small>تخصیص اتاق دانشگاه</small></span><button className="icon-button mobile-only" onClick={() => setOpen(false)}><X /></button></div>
      <nav>
        <NavLink to="/" end><LayoutDashboard /> نمای کلی</NavLink>
        <NavLink to="/runs/new"><Plus /> تخصیص جدید</NavLink>
        <NavLink to="/audit"><History /> تاریخچه فعالیت‌ها</NavLink>
      </nav>
      <div className="sidebar-foot"><div className="admin-chip"><span>{session?.username.slice(0, 1).toUpperCase()}</span><div><strong>{session?.username}</strong><small>مدیر سامانه</small></div></div><button className="logout" onClick={logout}><LogOut /> خروج</button></div>
    </aside>
    <div className="main-column"><header className="topbar"><button className="icon-button mobile-only" onClick={() => setOpen(true)}><Menu /></button><div><strong>سامانه تصمیم‌یار خوابگاه</strong><span className="system-online"><i /> سرویس فعال</span></div></header><div className="page-content">{children}</div></div>
    {open && <button aria-label="بستن منو" className="scrim" onClick={() => setOpen(false)} />}
    <PasswordChange />
  </div>;
}

function DataGrid<T>({ data, columns, empty = "داده‌ای برای نمایش وجود ندارد." }: { data: T[]; columns: ColumnDef<T>[]; empty?: string }) {
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });
  if (!data.length) return <div className="table-empty">{empty}</div>;
  return <div className="table-wrap"><table><thead>{table.getHeaderGroups().map((group) => <tr key={group.id}>{group.headers.map((header) => <th key={header.id}>{header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr>)}</thead><tbody>{table.getRowModel().rows.map((row) => <tr key={row.id}>{row.getVisibleCells().map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody></table></div>;
}

function RunsPage() {
  const query = useQuery({ queryKey: ["runs"], queryFn: runsApi.list, refetchInterval: 5_000 });
  const columns = useMemo<ColumnDef<Run>[]>(() => [
    { id: "dataset", header: "پرونده", cell: ({ row }) => <Link className="run-name" to={`/runs/${row.original.id}`}><strong>{row.original.dataset_filename}</strong><small>{row.original.student_count.toLocaleString("fa-IR")} دانشجو</small></Link> },
    { id: "status", header: "وضعیت", cell: ({ row }) => <StatusBadge status={row.original.status} /> },
    { id: "created_at", header: "تاریخ ایجاد", cell: ({ row }) => formatDate(row.original.created_at) },
    { id: "configuration", header: "پیکربندی", cell: ({ row }) => row.original.configuration.capacity_mode === "mixed" ? `${formatNumber(row.original.configuration.capacity_mix?.length ?? 0)} نوع اتاق` : `ظرفیت ${formatNumber(row.original.configuration.capacity ?? 6)} نفر` },
    { id: "minimum_utility", header: "کمترین امتیاز", cell: ({ row }) => formatNumber(row.original.metrics?.min_student_utility, 1) },
    { id: "runtime", header: "زمان اجرا", cell: ({ row }) => row.original.runtime_seconds ? `${formatNumber(row.original.runtime_seconds, 1)} ثانیه` : "—" },
    { id: "actions", header: "", cell: ({ row }) => <Link className="icon-link" aria-label="مشاهده اجرا" to={`/runs/${row.original.id}`}><ChevronLeft /></Link> },
  ], []);
  const runs = query.data ?? [];
  const completed = runs.filter((run) => run.status === "succeeded").length;
  const active = runs.filter((run) => ["queued", "running"].includes(run.status)).length;
  return <>
    <div className="page-heading"><div><p className="eyebrow">مرکز عملیات تخصیص</p><h1>اجراهای تخصیص اتاق</h1><p>وضعیت، کیفیت و خروجی تمام دوره‌های تخصیص را از یک نقطه مدیریت کنید.</p></div><Link className="button primary" to="/runs/new"><Plus /> تخصیص جدید</Link></div>
    <section className="metric-strip"><div><span className="metric-icon green"><ClipboardList /></span><p>کل اجراها<strong>{formatNumber(runs.length)}</strong></p></div><div><span className="metric-icon gold"><FileCheck2 /></span><p>تکمیل‌شده<strong>{formatNumber(completed)}</strong></p></div><div><span className="metric-icon blue"><Activity /></span><p>در حال پردازش<strong>{formatNumber(active)}</strong></p></div></section>
    <section className="panel"><div className="panel-head"><div><h2>تاریخچه اجراها</h2><p>جدیدترین اجراها در ابتدای فهرست قرار دارند.</p></div></div>{query.isLoading ? <Loading /> : query.isError ? <div className="alert danger">دریافت اجراها ممکن نبود.</div> : runs.length ? <DataGrid data={runs} columns={columns} /> : <EmptyState title="هنوز اجرایی ثبت نشده است" text="برای اعتبارسنجی داده‌ها و ساخت نخستین تخصیص شروع کنید." action={<Link className="button primary" to="/runs/new"><Plus /> ایجاد اولین تخصیص</Link>} />}</section>
  </>;
}

function Stepper({ step }: { step: number }) {
  return <div className="stepper">{["بارگذاری و اعتبارسنجی", "موجودی و تنظیمات", "تأیید و اجرا"].map((label, index) => <div className={step === index + 1 ? "active" : step > index + 1 ? "done" : ""} key={label}><span>{step > index + 1 ? "✓" : index + 1}</span><p>{label}</p></div>)}</div>;
}

function NewRunPage() {
  const navigate = useNavigate();
  const productConfig = useQuery({ queryKey: ["product-config"], queryFn: () => api<{ upload_limit_mb: number }>("/config") });
  const [step, setStep] = useState(1);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"uniform" | "mixed">("uniform");
  const [capacity, setCapacity] = useState(6);
  const [mix, setMix] = useState<CapacityEntry[]>([{ count: 100, capacity: 6 }, { count: 20, capacity: 4 }]);
  const [timeLimit, setTimeLimit] = useState(300);
  const [seed, setSeed] = useState(42);
  const [restarts, setRestarts] = useState(3);
  const [cpSat, setCpSat] = useState(false);
  const [sensitivity, setSensitivity] = useState(false);
  const [weights, setWeights] = useState({ cleanliness: 25, noise: 25, study: 25, schedule: 25 });
  const totalBeds = mix.reduce((sum, item) => sum + item.count * item.capacity, 0);
  const mutation = useMutation({
    mutationFn: async () => {
      const run = await runsApi.create({
        dataset_id: dataset!.id,
        configuration: { capacity_mode: mode, capacity, capacity_mix: mix, time_limit_seconds: timeLimit, seed, restarts, cp_sat_enabled: cpSat },
        scoring: { sensitivity_enabled: sensitivity, ...weights },
      });
      return runsApi.start(run.id);
    },
    onSuccess: (run) => navigate(`/runs/${run.id}`),
    onError: (reason: Error) => setError(reason.message),
  });
  const upload = async (file?: File) => {
    if (!file) return;
    setUploading(true); setError(""); setDataset(null);
    try { setDataset(await uploadDataset(file)); } catch (reason) { setError((reason as Error).message); } finally { setUploading(false); }
  };
  return <>
    <div className="page-heading compact"><div><Link className="back-link" to="/"><ArrowLeft /> بازگشت به اجراها</Link><h1>تخصیص جدید</h1><p>داده را اعتبارسنجی کنید و پس از مرور تنظیمات، اجرا را به صف بفرستید.</p></div></div>
    <Stepper step={step} />
    {error && <div className="alert danger"><CircleAlert />{error}</div>}
    {step === 1 && <section className="panel wizard-panel"><div className="section-title"><span>۱</span><div><h2>پرسشنامه دانشجویان</h2><p>فایل اصلی CSV یا Excel را بارگذاری کنید؛ فایل کدگذاری‌شده پذیرفته نمی‌شود.</p></div></div>
      <label className="drop-zone"><UploadCloud size={42} /><strong>{uploading ? "در حال بررسی فایل…" : "فایل را انتخاب کنید"}</strong><span>حداکثر {formatNumber(productConfig.data?.upload_limit_mb ?? 25)} مگابایت، با فرمت CSV یا XLSX</span><input type="file" accept=".csv,.xlsx" onChange={(event) => upload(event.target.files?.[0])} disabled={uploading} /></label>
      {dataset && <div className={`validation-card ${dataset.is_valid ? "valid" : "invalid"}`}><div><FileCheck2 /><div><strong>{dataset.original_filename}</strong><span>{formatNumber(dataset.row_count)} ردیف · {formatNumber(dataset.warning_count)} هشدار · {formatNumber(dataset.error_count)} خطا</span></div></div><StatusBadge status={dataset.is_valid ? "succeeded" : "failed"} /></div>}
      {dataset?.validation_issues.length ? <div className="validation-list">{dataset.validation_issues.slice(0, 20).map((issue, index) => <div key={index}><span className={`issue-dot ${issue.severity}`} /><strong>{String(issue.field ?? "dataset")}</strong><p>{String(issue.message ?? "")}</p></div>)}</div> : null}
      <div className="wizard-actions"><span /><button className="button primary" disabled={!dataset?.is_valid} onClick={() => setStep(2)}>ادامه تنظیمات <ChevronLeft /></button></div>
    </section>}
    {step === 2 && <section className="panel wizard-panel"><div className="section-title"><span>۲</span><div><h2>موجودی اتاق و سیاست اجرا</h2><p>سامانه کم‌ظرفیت‌ترین ترکیب کافی را انتخاب و اتاق‌های مازاد را غیرفعال می‌کند.</p></div></div>
      <div className="segmented"><button className={mode === "uniform" ? "active" : ""} onClick={() => setMode("uniform")}>ظرفیت یکسان</button><button className={mode === "mixed" ? "active" : ""} onClick={() => setMode("mixed")}>ظرفیت متغیر</button></div>
      {mode === "uniform" ? <div className="form-grid"><label>ظرفیت هر اتاق<input type="number" min={2} max={100} value={capacity} onChange={(e) => setCapacity(Number(e.target.value))} /></label></div> : <div className="inventory-editor"><div className="inventory-head"><strong>انواع اتاق</strong><button className="button secondary small" onClick={() => setMix([...mix, { count: 1, capacity: 2 }])}><Plus /> افزودن نوع</button></div>{mix.map((entry, index) => <div className="inventory-row" key={index}><label>تعداد<input type="number" min={1} value={entry.count} onChange={(e) => setMix(mix.map((item, itemIndex) => itemIndex === index ? { ...item, count: Number(e.target.value) } : item))} /></label><span>×</span><label>ظرفیت<input type="number" min={2} value={entry.capacity} onChange={(e) => setMix(mix.map((item, itemIndex) => itemIndex === index ? { ...item, capacity: Number(e.target.value) } : item))} /></label><button className="icon-button danger" disabled={mix.length === 1} onClick={() => setMix(mix.filter((_, itemIndex) => itemIndex !== index))}><Trash2 /></button></div>)}<div className={dataset && totalBeds < dataset.row_count ? "inventory-summary bad" : "inventory-summary"}><span>ظرفیت کل موجودی</span><strong>{formatNumber(totalBeds)} تخت</strong><small>{dataset ? `${formatNumber(dataset.row_count)} دانشجو` : ""}</small></div></div>}
      <div className="form-grid three"><label>محدودیت زمان (ثانیه)<input type="number" min={5} max={7200} value={timeLimit} onChange={(e) => setTimeLimit(Number(e.target.value))} /></label><label>بذر تصادفی<input type="number" min={0} value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></label><label>تعداد شروع مجدد<input type="number" min={1} max={20} value={restarts} onChange={(e) => setRestarts(Number(e.target.value))} /></label></div>
      <label className="switch-row"><input type="checkbox" checked={cpSat} onChange={(e) => setCpSat(e.target.checked)} /><span /><div><strong>بهبود محلی CP-SAT</strong><small>پس از تأیید معیار عملکرد در سرور دانشگاه فعال شود.</small></div></label>
      <label className="switch-row"><input type="checkbox" checked={sensitivity} onChange={(e) => setSensitivity(e.target.checked)} /><span /><div><strong>تحلیل حساسیت وزن‌ها</strong><small>وزن‌های تولیدی برابر می‌مانند مگر این گزینه فعال شود.</small></div></label>
      {sensitivity && <div className="form-grid four">{Object.entries(weights).map(([key, value]) => <label key={key}>{({ cleanliness: "نظافت", noise: "تحمل صدا", study: "مطالعه", schedule: "برنامه خواب" } as Record<string, string>)[key]}<input type="number" min={0} max={100} value={value} onChange={(e) => setWeights({ ...weights, [key]: Number(e.target.value) })} /></label>)}</div>}
      <div className="wizard-actions"><button className="button ghost" onClick={() => setStep(1)}><ChevronRight /> مرحله قبل</button><button className="button primary" disabled={mode === "mixed" && !!dataset && totalBeds < dataset.row_count} onClick={() => setStep(3)}>مرور نهایی <ChevronLeft /></button></div>
    </section>}
    {step === 3 && <section className="panel wizard-panel"><div className="section-title"><span>۳</span><div><h2>مرور و شروع تخصیص</h2><p>این تنظیمات همراه با نتیجه ذخیره می‌شوند و بعداً در تاریخچه در دسترس هستند.</p></div></div>
      <div className="review-grid"><div><span>فایل داده</span><strong>{dataset?.original_filename}</strong><small>{formatNumber(dataset?.row_count)} دانشجو</small></div><div><span>موجودی</span><strong>{mode === "uniform" ? `اتاق‌های ${capacity} نفره` : `${mix.length} نوع اتاق`}</strong><small>{mode === "mixed" ? `${formatNumber(totalBeds)} تخت موجود` : "تعداد اتاق خودکار"}</small></div><div><span>بودجه جست‌وجو</span><strong>{formatNumber(timeLimit)} ثانیه</strong><small>{formatNumber(restarts)} شروع مجدد</small></div><div><span>سیاست امتیاز</span><strong>{sensitivity ? "تحلیل حساسیت" : "وزن‌های تولیدی برابر"}</strong><small>ویژگی‌های حساس در امتیاز وارد نمی‌شوند</small></div></div>
      <div className="alert info"><ShieldCheck /> فایل، تنظیمات، نتیجه و دریافت خروجی‌ها در تاریخچه ثبت می‌شوند.</div>
      <div className="wizard-actions"><button className="button ghost" onClick={() => setStep(2)}><ChevronRight /> مرحله قبل</button><button className="button primary" disabled={mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? <LoaderCircle className="spin" /> : <Activity />} ارسال به صف تخصیص</button></div>
    </section>}
  </>;
}

function histogram(values: number[], bins = 12) {
  if (!values.length) return { labels: [], counts: [] };
  const min = Math.min(...values); const max = Math.max(...values); const width = Math.max((max - min) / bins, 1);
  const counts = Array.from({ length: bins }, () => 0);
  values.forEach((value) => { counts[Math.min(bins - 1, Math.floor((value - min) / width))] += 1; });
  return { labels: counts.map((_, index) => `${Math.round(min + index * width)}–${Math.round(min + (index + 1) * width)}`), counts };
}

function OverviewTab({ run }: { run: Run }) {
  const analytics = useQuery({ queryKey: ["analytics", run.id], queryFn: () => api<any>(`/runs/${run.id}/analytics`), enabled: run.status === "succeeded" });
  if (run.status !== "succeeded") return <RunProgress run={run} />;
  const metrics = run.metrics ?? {};
  const inventory = run.metadata?.room_inventory ?? {};
  const roomHistogram = histogram((analytics.data?.rooms ?? []).map((room: any) => room.room_quality));
  const studentHistogram = histogram(analytics.data?.student_utilities ?? []);
  return <><section className="metric-strip results"><div><p>کمترین امتیاز دانشجو<strong>{formatNumber(metrics.min_student_utility, 1)}</strong></p></div><div><p>صدک دهم کیفیت اتاق<strong>{formatNumber(metrics.p10_room_quality, 1)}</strong></p></div><div><p>میانگین امتیاز<strong>{formatNumber(metrics.mean_student_utility, 1)}</strong></p></div><div><p>زمان اجرا<strong>{formatNumber(run.runtime_seconds, 1)} ثانیه</strong></p></div></section>
    <section className="inventory-band"><div><BedDouble /><span>اتاق فعال<strong>{formatNumber(inventory.assigned_rooms)}</strong></span></div><div><span>اتاق استفاده‌نشده<strong>{formatNumber(inventory.unused_rooms)}</strong></span></div><div><span>تخت خالی فعال<strong>{formatNumber(inventory.active_vacancies)}</strong></span></div><div><span>کل دانشجویان<strong>{formatNumber(inventory.occupied_beds)}</strong></span></div></section>
    <div className="chart-grid"><section className="panel chart-panel"><div className="panel-head"><h2>توزیع کیفیت اتاق‌ها</h2></div><ReactECharts echarts={echarts} option={{ color: ["#2f7f75"], grid: { left: 45, right: 12, top: 20, bottom: 55 }, tooltip: {}, xAxis: { type: "category", data: roomHistogram.labels, axisLabel: { rotate: 35 } }, yAxis: { type: "value" }, series: [{ type: "bar", data: roomHistogram.counts, barMaxWidth: 32, itemStyle: { borderRadius: [5, 5, 0, 0] } }] }} /></section><section className="panel chart-panel"><div className="panel-head"><h2>توزیع امتیاز دانشجویان</h2></div><ReactECharts echarts={echarts} option={{ color: ["#b87945"], grid: { left: 45, right: 12, top: 20, bottom: 55 }, tooltip: {}, xAxis: { type: "category", data: studentHistogram.labels, axisLabel: { rotate: 35 } }, yAxis: { type: "value" }, series: [{ type: "bar", data: studentHistogram.counts, barMaxWidth: 32, itemStyle: { borderRadius: [5, 5, 0, 0] } }] }} /></section></div>
  </>;
}

function RunProgress({ run }: { run: Run }) {
  const phase = String(run.progress.message ?? run.progress.phase ?? "در انتظار شروع");
  return <section className="panel progress-panel"><div className={`progress-orbit ${run.status}`}><Activity /></div><StatusBadge status={run.status} /><h2>{phase}</h2><p>محاسبات در یک فرایند مستقل اجرا می‌شوند؛ می‌توانید این صفحه را ببندید و بعداً بازگردید.</p>{run.status === "failed" && <div className="alert danger">{run.error_message}</div>}<div className="progress-track"><span /></div></section>;
}

type RoomRow = {
  room_id: string;
  room_size: number;
  room_capacity: number;
  room_quality: number;
  mean_student_utility: number;
  cleanliness_contribution?: number;
  noise_contribution?: number;
  study_contribution?: number;
  schedule_contribution?: number;
};
type StudentRow = {
  room_id: string;
  bed: number;
  room_capacity: number;
  student_idx: number;
  student_id: string;
  student_name: string;
  student_utility: number;
  room_quality: number;
  faculty?: string | null;
  major?: string | null;
  age?: number | null;
  sleep_window?: number | null;
  wake_window?: number | null;
  noise_tolerance?: number | null;
  study_habit?: number | null;
  cleanliness?: number | null;
};
const AUDIT_LABELS: Record<string, string> = { login_succeeded: "ورود موفق", login_failed: "ورود ناموفق", logout: "خروج", password_changed: "تغییر رمز", dataset_uploaded: "بارگذاری داده", dataset_validated: "اعتبارسنجی داده", run_created: "ایجاد اجرا", run_queued: "ارسال به صف", run_started: "شروع اجرا", run_completed: "تکمیل اجرا", run_failed: "شکست اجرا", run_cancel_requested: "درخواست لغو", run_cancelled: "لغو اجرا", artifact_previewed: "پیش‌نمایش خروجی", artifact_downloaded: "دریافت خروجی", run_deleted: "حذف اجرا" };
const CONTRIBUTION_LABELS: Array<[keyof RoomRow, string]> = [
  ["cleanliness_contribution", "نظافت"],
  ["noise_contribution", "تحمل صدا"],
  ["study_contribution", "مطالعه"],
  ["schedule_contribution", "برنامه خواب"],
];
const SLEEP_LABELS = ["۲۲ تا ۲۳", "۲۳ تا ۲۴", "۲۴ تا ۱", "۱ تا ۲", "۲ تا ۳"];
const WAKE_LABELS = ["۴ تا ۵", "۵ تا ۶", "۶ تا ۷", "۷ تا ۸"];

function scheduleLabel(value: number | null | undefined, labels: string[]) {
  return value == null ? "ثبت نشده" : labels[value] ?? formatNumber(value);
}

function preferenceLabel(field: "noise_tolerance" | "study_habit" | "cleanliness", value: number | null | undefined) {
  if (value == null) return "ثبت نشده";
  if (field === "noise_tolerance") return value === 1 ? "محیط پرجنب‌وجوش" : "محیط آرام";
  if (field === "study_habit") return value === 1 ? "مطالعه در سکوت" : "مطالعه با صدا";
  return value === 1 ? "نظم‌طلب" : "راحت‌طلب";
}

function ProfileChips({ student, compact = false }: { student: StudentRow; compact?: boolean }) {
  const items = compact
    ? [preferenceLabel("cleanliness", student.cleanliness), preferenceLabel("noise_tolerance", student.noise_tolerance)]
    : [
      preferenceLabel("cleanliness", student.cleanliness),
      preferenceLabel("noise_tolerance", student.noise_tolerance),
      preferenceLabel("study_habit", student.study_habit),
      `خواب ${scheduleLabel(student.sleep_window, SLEEP_LABELS)}`,
      `بیداری ${scheduleLabel(student.wake_window, WAKE_LABELS)}`,
    ];
  return <span className="profile-chips">{items.map((item) => <small key={item}>{item}</small>)}</span>;
}

function RoomContributions({ room }: { room: RoomRow }) {
  const values = CONTRIBUTION_LABELS.map(([key, label]) => ({ label, value: Number(room[key] ?? 0) }));
  const palette = ["#2f7f75", "#6aa399", "#b87945", "#d5a979"];
  return <div className="contribution-block"><div className="contribution-bar" aria-label="ترکیب امتیاز معیارهای اتاق">{values.map((item, index) => <span key={item.label} style={{ width: `${Math.max(0, item.value)}%`, background: palette[index] }} />)}</div><div className="contribution-legend">{values.map((item, index) => <div key={item.label}><i style={{ background: palette[index] }} /><span>{item.label}</span><strong>{formatNumber(item.value, 1)}</strong></div>)}</div></div>;
}

const RESIDENT_CRITERIA = [
  { key: "cleanliness", label: "نظافت", value: (student: StudentRow) => preferenceLabel("cleanliness", student.cleanliness) },
  { key: "noise_tolerance", label: "تحمل صدا", value: (student: StudentRow) => preferenceLabel("noise_tolerance", student.noise_tolerance) },
  { key: "study_habit", label: "عادت مطالعه", value: (student: StudentRow) => preferenceLabel("study_habit", student.study_habit) },
  { key: "sleep_window", label: "زمان خواب", value: (student: StudentRow) => scheduleLabel(student.sleep_window, SLEEP_LABELS) },
  { key: "wake_window", label: "زمان بیداری", value: (student: StudentRow) => scheduleLabel(student.wake_window, WAKE_LABELS) },
] as const;

function ResidentComparison({ students }: { students: StudentRow[] }) {
  return <div className="resident-comparison">
    <div className="comparison-summary" aria-label="خلاصه مقایسه معیارهای ساکنان">
      {RESIDENT_CRITERIA.map((criterion) => {
        const values = new Set(students.map(criterion.value).filter((value) => value !== "ثبت نشده"));
        const isSame = values.size === 1 && students.length > 1;
        return <div key={criterion.key} className={isSame ? "same" : "varied"}>
          <span>{criterion.label}</span>
          <strong>{isSame ? "یکسان" : values.size > 1 ? `${formatNumber(values.size)} الگوی متفاوت` : "نیازمند داده"}</strong>
        </div>;
      })}
    </div>
    <div className="comparison-table-wrap">
      <table className="comparison-table">
        <thead><tr><th>ساکن</th>{RESIDENT_CRITERIA.map((criterion) => <th key={criterion.key}>{criterion.label}</th>)}<th>امتیاز فردی</th></tr></thead>
        <tbody>{students.map((student) => <tr key={student.student_idx}>
          <th scope="row"><span className="resident-identity"><span className="bed-number">{formatNumber(student.bed)}</span><span><strong>{student.student_name}</strong><small>{student.student_id}</small></span></span></th>
          {RESIDENT_CRITERIA.map((criterion) => <td key={criterion.key}><span className="comparison-value">{criterion.value(student)}</span></td>)}
          <td><strong className="comparison-score">{formatNumber(student.student_utility, 1)}</strong></td>
        </tr>)}</tbody>
      </table>
    </div>
  </div>;
}

function InspectorFrame({ title, subtitle, onClose, children, wide = false }: { title: string; subtitle: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => { document.body.style.overflow = previousOverflow; window.removeEventListener("keydown", closeOnEscape); };
  }, [onClose]);
  return <div className="inspector-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className={`inspector${wide ? " inspector-wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}><header><div><p className="eyebrow">نمای بازرسی</p><h2>{title}</h2><span>{subtitle}</span></div><button className="icon-button" aria-label="بستن جزئیات" onClick={onClose}><X /></button></header><div className="inspector-body">{children}</div></section></div>;
}

function RoomInspector({ runId, room, onClose }: { runId: string; room: RoomRow; onClose: () => void }) {
  const residents = useQuery({ queryKey: ["room-residents", runId, room.room_id], queryFn: () => api<Page<StudentRow>>(`/runs/${runId}/students?room_id=${encodeURIComponent(room.room_id)}&offset=0&limit=500`) });
  const students = residents.data?.items ?? [];
  return <InspectorFrame title={`اتاق ${room.room_id}`} subtitle={`${formatNumber(room.room_size)} ساکن از ظرفیت ${formatNumber(room.room_capacity)} نفر`} onClose={onClose} wide>
    <div className="inspector-metrics"><div><span>کیفیت اتاق</span><strong>{formatNumber(room.room_quality, 1)}</strong></div><div><span>میانگین امتیاز ساکنان</span><strong>{formatNumber(room.mean_student_utility, 1)}</strong></div><div><span>تخت خالی</span><strong>{formatNumber(room.room_capacity - room.room_size)}</strong></div></div>
    <section className="inspector-section"><div className="inspector-section-title"><h3>اجزای کیفیت اتاق</h3><small>سهم هر معیار از امتیاز نهایی ۱۰۰</small></div><RoomContributions room={room} /></section>
    <section className="inspector-section"><div className="inspector-section-title"><div><h3>مقایسه ساکنان اتاق</h3><p>معیارهای مؤثر در تخصیص هر دانشجو را در یک ردیف مقایسه کنید.</p></div><small>{formatNumber(residents.data?.total ?? room.room_size)} دانشجو</small></div>{residents.isLoading ? <Loading label="دریافت فهرست ساکنان" /> : students.length ? <ResidentComparison students={students} /> : <div className="inline-empty">اطلاعات ساکنان این اتاق در دسترس نیست.</div>}</section>
  </InspectorFrame>;
}

function StudentInspector({ runId, student, onClose }: { runId: string; student: StudentRow; onClose: () => void }) {
  const room = useQuery({ queryKey: ["student-room", runId, student.room_id], queryFn: () => api<Page<StudentRow>>(`/runs/${runId}/students?room_id=${encodeURIComponent(student.room_id)}&offset=0&limit=500`) });
  const roommates = (room.data?.items ?? []).filter((item) => item.student_idx !== student.student_idx);
  return <InspectorFrame title={student.student_name} subtitle={`${student.student_id} · اتاق ${student.room_id} · تخت ${formatNumber(student.bed)}`} onClose={onClose}>
    <div className="inspector-metrics"><div><span>امتیاز فردی</span><strong>{formatNumber(student.student_utility, 1)}</strong></div><div><span>کیفیت اتاق</span><strong>{formatNumber(student.room_quality, 1)}</strong></div><div><span>هم‌اتاقی</span><strong>{formatNumber(Math.max(0, (room.data?.total ?? 1) - 1))}</strong></div></div>
    <section className="inspector-section"><div className="inspector-section-title"><h3>پروفایل و ترجیحات</h3><small>فقط ویژگی‌های غیرحساس مورد استفاده در تخصیص</small></div><dl className="profile-grid"><div><dt>دانشکده</dt><dd>{student.faculty || "ثبت نشده"}</dd></div><div><dt>رشته</dt><dd>{student.major || "ثبت نشده"}</dd></div><div><dt>سن</dt><dd>{student.age == null ? "ثبت نشده" : `${formatNumber(student.age)} سال`}</dd></div><div><dt>زمان خواب</dt><dd>{scheduleLabel(student.sleep_window, SLEEP_LABELS)}</dd></div><div><dt>زمان بیداری</dt><dd>{scheduleLabel(student.wake_window, WAKE_LABELS)}</dd></div><div><dt>نظافت</dt><dd>{preferenceLabel("cleanliness", student.cleanliness)}</dd></div><div><dt>تحمل صدا</dt><dd>{preferenceLabel("noise_tolerance", student.noise_tolerance)}</dd></div><div><dt>عادت مطالعه</dt><dd>{preferenceLabel("study_habit", student.study_habit)}</dd></div></dl></section>
    <section className="inspector-section"><div className="inspector-section-title"><h3>ترکیب هم‌اتاقی‌ها</h3><small>برای بررسی سریع زمینه امتیاز فردی</small></div>{room.isLoading ? <Loading label="دریافت هم‌اتاقی‌ها" /> : roommates.length ? <div className="resident-list roommates">{roommates.map((item) => <article key={item.student_idx}><span className="bed-number">{formatNumber(item.bed)}</span><div><strong>{item.student_name}</strong><small>{item.student_id}</small><ProfileChips student={item} compact /></div><span className="resident-score"><small>امتیاز</small><strong>{formatNumber(item.student_utility, 1)}</strong></span></article>)}</div> : <div className="inline-empty">این دانشجو هم‌اتاقی ندارد.</div>}</section>
  </InspectorFrame>;
}

function Pager({ page, limit, total, setPage }: { page: number; limit: number; total: number; setPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / limit));
  return <div className="pager"><span>صفحه {formatNumber(page + 1)} از {formatNumber(pages)} · {formatNumber(total)} مورد</span><div><button className="icon-button" disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronRight /></button><button className="icon-button" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}><ChevronLeft /></button></div></div>;
}

function RoomsTab({ runId }: { runId: string }) {
  const [query, setQuery] = useState(""); const [page, setPage] = useState(0); const [minQuality, setMinQuality] = useState(""); const [maxQuality, setMaxQuality] = useState(""); const [selected, setSelected] = useState<RoomRow | null>(null); const limit = 50;
  const qualityParams = `${minQuality ? `&min_quality=${encodeURIComponent(minQuality)}` : ""}${maxQuality ? `&max_quality=${encodeURIComponent(maxQuality)}` : ""}`;
  const result = useQuery({ queryKey: ["rooms", runId, query, minQuality, maxQuality, page], queryFn: () => api<Page<RoomRow>>(`/runs/${runId}/rooms?query=${encodeURIComponent(query)}${qualityParams}&offset=${page * limit}&limit=${limit}`) });
  const columns = useMemo<ColumnDef<RoomRow>[]>(() => [
    { accessorKey: "room_id", header: "اتاق", cell: ({ getValue }) => <strong>{getValue<string>()}</strong> },
    { id: "occupancy", header: "اشغال", cell: ({ row }) => <span className="occupancy-cell"><span><i style={{ width: `${(row.original.room_size / row.original.room_capacity) * 100}%` }} /></span><small>{formatNumber(row.original.room_size)} از {formatNumber(row.original.room_capacity)}</small></span> },
    { accessorKey: "room_quality", header: "کیفیت", cell: ({ getValue }) => <strong className="score">{formatNumber(getValue<number>(), 1)}</strong> },
    { accessorKey: "mean_student_utility", header: "میانگین امتیاز", cell: ({ getValue }) => formatNumber(getValue<number>(), 1) },
    { id: "dominant", header: "قوی‌ترین معیار", cell: ({ row }) => { const item = CONTRIBUTION_LABELS.map(([key, label]) => ({ label, value: Number(row.original[key] ?? 0) })).sort((a, b) => b.value - a.value)[0]; return <span className="criterion-cell"><strong>{item.label}</strong><small>{formatNumber(item.value, 1)} امتیاز</small></span>; } },
    { id: "inspect", header: "", cell: ({ row }) => <button className="inspect-button" onClick={() => setSelected(row.original)}><Eye /> جزئیات</button> },
  ], []);
  return <><section className="panel"><div className="panel-head result-head"><div><h2>اتاق‌های تخصیص‌یافته</h2><p>اتاق‌های ضعیف‌تر ابتدا نمایش داده می‌شوند؛ برای مشاهده ترکیب هر اتاق جزئیات را باز کنید.</p></div><div className="result-filters"><label className="search"><Search /><input placeholder="جست‌وجوی شناسه اتاق" value={query} onChange={(e) => { setQuery(e.target.value); setPage(0); }} /></label><label className="range-filter"><span>کیفیت از</span><input aria-label="حداقل کیفیت" type="number" min="0" max="100" placeholder="۰" value={minQuality} onChange={(e) => { setMinQuality(e.target.value); setPage(0); }} /></label><label className="range-filter"><span>تا</span><input aria-label="حداکثر کیفیت" type="number" min="0" max="100" placeholder="۱۰۰" value={maxQuality} onChange={(e) => { setMaxQuality(e.target.value); setPage(0); }} /></label></div></div>{result.isLoading ? <Loading /> : <DataGrid data={result.data?.items ?? []} columns={columns} />}<Pager page={page} limit={limit} total={result.data?.total ?? 0} setPage={setPage} /></section>{selected && <RoomInspector runId={runId} room={selected} onClose={() => setSelected(null)} />}</>;
}

function StudentsTab({ runId }: { runId: string }) {
  const [query, setQuery] = useState(""); const [page, setPage] = useState(0); const [selected, setSelected] = useState<StudentRow | null>(null); const limit = 50;
  const result = useQuery({ queryKey: ["students", runId, query, page], queryFn: () => api<Page<StudentRow>>(`/runs/${runId}/students?query=${encodeURIComponent(query)}&offset=${page * limit}&limit=${limit}`) });
  const columns = useMemo<ColumnDef<StudentRow>[]>(() => [
    { id: "student", header: "دانشجو", cell: ({ row }) => <span className="student-cell"><strong>{row.original.student_name}</strong><small>{row.original.student_id}{row.original.major ? ` · ${row.original.major}` : ""}</small></span> },
    { id: "placement", header: "جانمایی", cell: ({ row }) => <span className="criterion-cell"><strong>اتاق {row.original.room_id}</strong><small>تخت {formatNumber(row.original.bed)} از {formatNumber(row.original.room_capacity)}</small></span> },
    { id: "profile", header: "خلاصه ترجیحات", cell: ({ row }) => <ProfileChips student={row.original} compact /> },
    { accessorKey: "student_utility", header: "امتیاز فردی", cell: ({ getValue }) => <strong className="score">{formatNumber(getValue<number>(), 1)}</strong> },
    { id: "inspect", header: "", cell: ({ row }) => <button className="inspect-button" onClick={() => setSelected(row.original)}><Eye /> مشاهده</button> },
  ], []);
  return <><section className="panel"><div className="panel-head"><div><h2>دانشجویان</h2><p>دانشجویان با امتیاز کمتر در ابتدای فهرست هستند؛ نمای کامل، ترجیحات و هم‌اتاقی‌ها را نشان می‌دهد.</p></div><label className="search"><Search /><input placeholder="نام، شناسه یا اتاق" value={query} onChange={(e) => { setQuery(e.target.value); setPage(0); }} /></label></div>{result.isLoading ? <Loading /> : <DataGrid data={result.data?.items ?? []} columns={columns} />}<Pager page={page} limit={limit} total={result.data?.total ?? 0} setPage={setPage} /></section>{selected && <StudentInspector runId={runId} student={selected} onClose={() => setSelected(null)} />}</>;
}

type ArtifactPreview = {
  kind: "table" | "json";
  filename: string;
  columns?: string[];
  rows?: Array<Record<string, unknown>>;
  total_rows?: number;
  sheets?: string[];
  sheet?: string | null;
  truncated?: boolean;
  data?: unknown;
};

type ExportDescription = { title: string; description: string; purpose: string };

const EXPORT_COPY: Record<string, ExportDescription> = {
  "unimate_report.xlsx": { title: "گزارش کامل تخصیص‌ها", description: "همه اطلاعات تخصیص در چند برگه مرتب", purpose: "مناسب بررسی کامل و کار با Excel" },
  "unimate_report.pdf": { title: "گزارش آماده ارائه", description: "خلاصه رسمی نتایج با چیدمان آماده چاپ", purpose: "مناسب ارائه به مدیریت و چاپ" },
  "assignments.csv": { title: "فهرست تخصیص دانشجویان", description: "نام دانشجو، اتاق و تخت اختصاص‌یافته", purpose: "مناسب تحویل به مسئول اسکان" },
  "room_metrics.csv": { title: "گزارش وضعیت اتاق‌ها", description: "ظرفیت، تعداد ساکنان و کیفیت هر اتاق", purpose: "مناسب بررسی ظرفیت و کیفیت اتاق‌ها" },
  "student_metrics.csv": { title: "گزارش وضعیت دانشجویان", description: "امتیاز و نتیجه تخصیص هر دانشجو", purpose: "مناسب بررسی عدالت تخصیص" },
  "validation_report.csv": { title: "گزارش بررسی داده‌ها", description: "خطاها و هشدارهای فایل ورودی", purpose: "مناسب اصلاح پرسشنامه و داده‌ها" },
  "run_metadata.json": { title: "اطلاعات فنی تخصیص", description: "تنظیمات و مشخصات بازتولید این اجرا", purpose: "مناسب مستندسازی و بازتولید نتیجه" },
};

function fileSizeLabel(bytes?: number) {
  if (bytes == null) return "";
  if (bytes < 1024) return `${formatNumber(bytes)} بایت`;
  if (bytes < 1024 * 1024) return `${formatNumber(bytes / 1024, 1)} کیلوبایت`;
  return `${formatNumber(bytes / (1024 * 1024), 1)} مگابایت`;
}

function previewCell(value: unknown) {
  if (value == null || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function PdfArtifactPreview({ url }: { url: string }) {
  const [source, setSource] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let objectUrl = "";
    const controller = new AbortController();
    fetch(url, { credentials: "include", signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error("پیش‌نمایش PDF در دسترس نیست."); return response.blob(); })
      .then((blob) => { objectUrl = URL.createObjectURL(blob); setSource(objectUrl); })
      .catch((reason: Error) => { if (reason.name !== "AbortError") setError(reason.message); });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [url]);
  if (error) return <div className="alert danger">{error}</div>;
  if (!source) return <Loading label="آماده‌سازی پیش‌نمایش PDF" />;
  return <iframe className="pdf-preview" src={source} title="پیش‌نمایش گزارش PDF" />;
}

function ArtifactPreviewDialog({ runId, name, description, onClose }: { runId: string; name: string; description: ExportDescription; onClose: () => void }) {
  const isPdf = name.toLowerCase().endsWith(".pdf");
  const [sheet, setSheet] = useState("");
  const [query, setQuery] = useState("");
  const previewPath = `/runs/${runId}/artifacts/${encodeURIComponent(name)}/preview${sheet ? `?sheet=${encodeURIComponent(sheet)}` : ""}`;
  const preview = useQuery({ queryKey: ["artifact-preview", runId, name, sheet], queryFn: () => api<ArtifactPreview>(previewPath), enabled: !isPdf });
  const rows = preview.data?.rows ?? [];
  const normalizedQuery = query.trim().toLocaleLowerCase("fa");
  const visibleRows = normalizedQuery ? rows.filter((row) => Object.values(row).some((value) => previewCell(value).toLocaleLowerCase("fa").includes(normalizedQuery))) : rows;
  const downloadUrl = `/api/runs/${runId}/artifacts/${encodeURIComponent(name)}`;
  const pdfUrl = `/api/runs/${runId}/artifacts/${encodeURIComponent(name)}/preview`;
  return <InspectorFrame title={description.title} subtitle={description.purpose} onClose={onClose} wide>
    <div className="preview-actions"><div><span className="file-type">{name.split(".").pop()?.toUpperCase()}</span><small>{name}</small></div><a className="button primary small" href={downloadUrl}><Download /> دانلود فایل</a></div>
    {isPdf ? <PdfArtifactPreview url={pdfUrl} /> : preview.isLoading ? <Loading label="دریافت محتوای گزارش" /> : preview.isError ? <div className="alert danger">{(preview.error as Error).message}</div> : preview.data?.kind === "json" ? <pre className="json-preview">{JSON.stringify(preview.data.data, null, 2)}</pre> : <>
      <div className="preview-toolbar">
        {(preview.data?.sheets?.length ?? 0) > 1 && <label><span>برگه Excel</span><select value={preview.data?.sheet ?? ""} onChange={(event) => { setSheet(event.target.value); setQuery(""); }}>{preview.data?.sheets?.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>}
        <label className="search"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="جست‌وجو در ردیف‌های پیش‌نمایش" /></label>
        <small>{formatNumber(visibleRows.length)} ردیف نمایش داده شده از {formatNumber(preview.data?.total_rows ?? 0)}</small>
      </div>
      <div className="artifact-preview-table"><table><thead><tr>{preview.data?.columns?.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{visibleRows.map((row, index) => <tr key={index}>{preview.data?.columns?.map((column) => <td key={column}>{previewCell(row[column])}</td>)}</tr>)}</tbody></table>{!visibleRows.length && <div className="inline-empty">ردیفی مطابق جست‌وجوی شما پیدا نشد.</div>}</div>
      {preview.data?.truncated && <p className="preview-note">برای حفظ سرعت، فقط {formatNumber(rows.length)} ردیف نخست پیش‌نمایش داده می‌شود؛ فایل دانلودی شامل همه ردیف‌هاست.</p>}
    </>}
  </InspectorFrame>;
}

function ExportsTab({ run }: { run: Run }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const entries = Object.entries(run.artifacts).filter(([name]) => {
    const item = EXPORT_COPY[name] ?? { title: "گزارش تکمیلی", description: "اطلاعات تکمیلی این تخصیص", purpose: "مناسب بررسی تکمیلی" };
    const haystack = `${name} ${item.title} ${item.description} ${item.purpose}`.toLocaleLowerCase("fa");
    return haystack.includes(query.trim().toLocaleLowerCase("fa"));
  });
  return <><section className="panel"><div className="panel-head export-heading"><div><h2>مرور خروجی‌ها</h2><p>ابتدا محتوای هر گزارش را ببینید و بعد فایل مناسب را دریافت کنید.</p></div><label className="search"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="جست‌وجوی گزارش یا کاربرد آن" /></label></div><div className="report-finder"><strong>راهنمای انتخاب سریع</strong><span>ارائه رسمی: PDF</span><span>بررسی کامل: Excel</span><span>تحلیل جزئی: CSV</span><span>بازتولید: JSON</span></div><div className="export-grid">{entries.map(([name, manifest]) => { const item = EXPORT_COPY[name] ?? { title: "گزارش تکمیلی", description: "اطلاعات تکمیلی این تخصیص", purpose: "مناسب بررسی تکمیلی" }; const extension = name.split(".").pop()?.toUpperCase(); return <article className="export-card" key={name}><span className="export-icon"><FileCheck2 /></span><div className="export-copy"><span className="export-meta"><b>{extension}</b>{fileSizeLabel(manifest.size)}</span><strong>{item.title}</strong><small>{item.description}</small><em>{item.purpose}</em></div><div className="export-actions"><button className="button secondary small" onClick={() => setSelected(name)}><Eye /> پیش‌نمایش</button><a className="button ghost small" href={`/api/runs/${run.id}/artifacts/${encodeURIComponent(name)}`}><Download /> دانلود</a></div></article>; })}{!entries.length && <div className="inline-empty export-empty">گزارشی مطابق جست‌وجوی شما پیدا نشد.</div>}</div></section>{selected && <ArtifactPreviewDialog key={selected} runId={run.id} name={selected} description={EXPORT_COPY[selected] ?? { title: "گزارش تکمیلی", description: "اطلاعات تکمیلی این تخصیص", purpose: "مناسب بررسی تکمیلی" }} onClose={() => setSelected(null)} />}</>;
}

function RunAuditTab({ runId }: { runId: string }) {
  const result = useQuery({ queryKey: ["audit", runId], queryFn: () => api<Page<any>>(`/audit?entity_id=${encodeURIComponent(runId)}&limit=200`) });
  return <section className="panel"><div className="panel-head"><div><h2>تاریخچه این اجرا</h2><p>شروع، لغو، تکمیل و دریافت خروجی‌های همین اجرا نمایش داده می‌شود.</p></div></div><div className="audit-list">{result.isLoading ? <Loading /> : (result.data?.items ?? []).map((event) => <div className="audit-row" key={event.id}><span className="audit-dot" /><div><strong>{AUDIT_LABELS[event.action] ?? event.action}</strong><small>{event.details?.artifact ? String(event.details.artifact) : `شناسه ${runId.slice(0, 8)}`}</small></div><time>{formatDate(event.created_at)}</time></div>)}</div></section>;
}

function RunWorkspace({ runId }: { runId: string }) {
  const navigate = useNavigate(); const client = useQueryClient(); const [tab, setTab] = useState("overview");
  const result = useQuery({ queryKey: ["run", runId], queryFn: () => runsApi.get(runId), refetchInterval: (query) => ["queued", "running"].includes(query.state.data?.status ?? "") ? 2_000 : false });
  useEffect(() => {
    if (!result.data || !["queued", "running"].includes(result.data.status)) return;
    const stream = new EventSource(`/api/runs/${runId}/events`, { withCredentials: true });
    stream.addEventListener("progress", () => client.invalidateQueries({ queryKey: ["run", runId] }));
    return () => stream.close();
  }, [result.data?.status, runId, client]);
  const cancel = useMutation({ mutationFn: () => runsApi.cancel(runId), onSuccess: () => client.invalidateQueries({ queryKey: ["run", runId] }) });
  const remove = useMutation({ mutationFn: () => runsApi.delete(runId), onSuccess: () => { client.invalidateQueries({ queryKey: ["runs"] }); navigate("/"); } });
  if (result.isLoading) return <Loading />;
  if (!result.data) return <EmptyState title="اجرا پیدا نشد" text="ممکن است این اجرا حذف شده باشد." />;
  const run = result.data;
  const tabs = [{ id: "overview", label: "نمای کلی" }, { id: "rooms", label: "اتاق‌ها" }, { id: "students", label: "دانشجویان" }, { id: "audit", label: "تاریخچه" }, { id: "exports", label: "خروجی‌ها" }];
  return <><div className="page-heading compact"><div><Link className="back-link" to="/"><ArrowLeft /> بازگشت به اجراها</Link><div className="title-line"><h1>{run.dataset_filename}</h1><StatusBadge status={run.status} /></div><p>{formatNumber(run.student_count)} دانشجو · ایجاد در {formatDate(run.created_at)} · شناسه {run.id.slice(0, 8)}</p></div><div className="heading-actions">{["queued", "running"].includes(run.status) && <button className="button secondary" onClick={() => cancel.mutate()}><X /> لغو اجرا</button>}{["draft", "succeeded", "failed", "cancelled"].includes(run.status) && <button className="button danger-outline" onClick={() => window.confirm("این اجرا و داده‌های وابسته به‌طور دائمی حذف شوند؟") && remove.mutate()}><Trash2 /> حذف</button>}</div></div>
    <div className="tabs">{tabs.map((item) => <button className={tab === item.id ? "active" : ""} disabled={!['overview', 'audit'].includes(item.id) && run.status !== "succeeded"} onClick={() => setTab(item.id)} key={item.id}>{item.label}</button>)}</div>
    {tab === "overview" && <OverviewTab run={run} />}{tab === "rooms" && <RoomsTab runId={runId} />}{tab === "students" && <StudentsTab runId={runId} />}{tab === "audit" && <RunAuditTab runId={runId} />}{tab === "exports" && <ExportsTab run={run} />}
  </>;
}

function RunDetailPage() { const { id } = useParams(); return id ? <RunWorkspace key={id} runId={id} /> : <Navigate to="/" />; }

function AuditPage() {
  const result = useQuery({ queryKey: ["audit"], queryFn: () => api<Page<any>>("/audit?limit=200") });
  return <><div className="page-heading"><div><p className="eyebrow">فعالیت‌های سامانه</p><h1>تاریخچه فعالیت‌ها</h1><p>فعالیت‌های امنیتی و عملیاتی بدون ثبت اطلاعات شخصی دانشجویان نگهداری می‌شوند.</p></div></div><section className="panel audit-list">{result.isLoading ? <Loading /> : (result.data?.items ?? []).map((event) => <div className="audit-row" key={event.id}><span className="audit-dot" /><div><strong>{AUDIT_LABELS[event.action] ?? event.action}</strong><small>{event.entity_type}{event.entity_id ? ` · ${String(event.entity_id).slice(0, 8)}` : ""}</small></div><time>{formatDate(event.created_at)}</time></div>)}</section></>;
}

function Protected({ children }: { children: ReactNode }) {
  const { session } = useContext(AuthContext);
  return session ? <Shell>{children}</Shell> : <Navigate to="/login" replace />;
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { authApi.me().then((value) => { setCsrfToken(value.csrf_token); setSession(value); }).catch(() => setSession(null)).finally(() => setLoading(false)); }, []);
  if (loading) return <div className="splash"><span className="brand-mark"><BedDouble /></span><Loading label="در حال آماده‌سازی یونی‌میت" /></div>;
  return <AuthContext.Provider value={{ session, setSession }}><Routes><Route path="/login" element={session ? <Navigate to="/" replace /> : <LoginPage />} /><Route path="/" element={<Protected><RunsPage /></Protected>} /><Route path="/runs/new" element={<Protected><NewRunPage /></Protected>} /><Route path="/runs/:id" element={<Protected><RunDetailPage /></Protected>} /><Route path="/audit" element={<Protected><AuditPage /></Protected>} /><Route path="*" element={<Navigate to="/" replace />} /></Routes></AuthContext.Provider>;
}
