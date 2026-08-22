import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Database,
  Download,
  KeyRound,
  Loader2,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  WalletCards,
  WifiOff,
} from "lucide-react";
import { PortfolioSourceEditor } from "@/components/portfolio/PortfolioSourceEditor";
import {
  api,
  type PortfolioAccount,
  type PortfolioHistoryPoint,
  type PortfolioRefreshState,
  type PortfolioSettings,
  type PortfolioSnapshot,
  type PortfolioSourceCatalogItem,
} from "@/lib/api";
import { echarts } from "@/lib/echarts";

const BROKER_COLORS: Record<string, string> = {
  IBKR: "#f05a47",
  LONGBRIDGE: "#4f6edb",
  BINANCE: "#f3ba2f",
};

const HOLDING_COLORS = [
  "#4f6edb", "#f3ba2f", "#45a67d", "#8b6fd6", "#ef8354",
  "#2d9cdb", "#d96c9d", "#7f8c8d", "#b5c83b", "#f05a47",
];

function money(value: number | undefined, currency: "USD" | "CNY" = "USD") {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: currency === "USD" ? 2 : 0,
  }).format(value);
}

function quantity(value: number | undefined) {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 8 }).format(value);
}

function price(value: number | undefined | null) {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: value >= 1 ? 2 : 4,
    maximumFractionDigits: value >= 100 ? 2 : value >= 1 ? 4 : 8,
  }).format(value);
}

function percentage(value: number | undefined) {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function dateTime(value: string | undefined) {
  return value ? new Date(value).toLocaleString() : "—";
}

function dayKey(value: string) {
  const date = new Date(value);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

export function Portfolio() {
  const { i18n } = useTranslation();
  const zh = i18n.language.startsWith("zh");
  const [snapshot, setSnapshot] = useState<PortfolioSnapshot | null>(null);
  const [history, setHistory] = useState<PortfolioHistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [refreshState, setRefreshState] = useState<PortfolioRefreshState | null>(null);
  const [portfolioSettings, setPortfolioSettings] = useState<PortfolioSettings | null>(null);
  const [sourceCatalog, setSourceCatalog] = useState<PortfolioSourceCatalogItem[]>([]);
  const [editorOpen, setEditorOpen] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<string>("all");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [current, points, configuration] = await Promise.all([
        api.getPortfolio(),
        api.getPortfolioHistory(),
        api.getPortfolioSettings(),
      ]);
      setSnapshot(current.snapshot);
      setHistory(points.history ?? []);
      setPortfolioSettings(configuration.settings);
      setSourceCatalog(configuration.catalog);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Portfolio unavailable");
    } finally {
      setLoading(false);
    }
  }

  async function refresh(settingsOverride?: PortfolioSettings) {
    const activeSettings = settingsOverride ?? portfolioSettings;
    const enabledSources = activeSettings?.sources.filter((source) => source.enabled) ?? [];
    if (!enabledSources.length) {
      setEditorOpen(true);
      return;
    }
    setRefreshing(true);
    setError(null);
    setRefreshState({
      running: true,
      current: null,
      sources: Object.fromEntries(enabledSources.map((source) => [source.connection_id, { status: "pending" as const }])),
    });
    const timer = window.setInterval(() => {
      void api.getPortfolioRefreshStatus()
        .then((result) => setRefreshState(normalizeRefreshState(result.refresh)))
        .catch(() => undefined);
    }, 500);
    try {
      const result = await api.refreshPortfolio();
      setSnapshot(result.snapshot);
      const points = await api.getPortfolioHistory();
      setHistory(points.history ?? []);
      const status = await api.getPortfolioRefreshStatus();
      setRefreshState(normalizeRefreshState(status.refresh));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      window.clearInterval(timer);
      setRefreshing(false);
    }
  }

  async function reconnectSource(sourceId: string) {
    setReconnecting(true);
    setError(null);
    try {
      await api.reconnectPortfolioSource(sourceId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Account reconnect failed");
    } finally {
      setReconnecting(false);
    }
  }

  async function savePortfolioSettings(settings: PortfolioSettings) {
    setSavingSettings(true);
    setError(null);
    try {
      const result = await api.updatePortfolioSettings(settings);
      setPortfolioSettings(result.settings);
      setSourceCatalog(result.catalog);
      setEditorOpen(false);
      setSourceFilter("all");
      if (result.settings.sources.some((source) => source.enabled)) {
        await refresh(result.settings);
      } else {
        setSnapshot(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save portfolio settings");
    } finally {
      setSavingSettings(false);
    }
  }

  async function reloadConnections() {
    const configuration = await api.getPortfolioSettings();
    setPortfolioSettings(configuration.settings);
    setSourceCatalog(configuration.catalog);
  }

  async function download() {
    try {
      const blob = await api.downloadPortfolioCsv();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `portfolio-${new Date().toISOString().slice(0, 10)}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    }
  }

  useEffect(() => { void load(); }, []);

  const positions = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return [...(snapshot?.positions ?? [])]
      .filter((row) => sourceFilter === "all" || (row.source_id ?? row.broker) === sourceFilter)
      .filter((row) => !needle || [row.broker, row.symbol, row.name, row.asset_type, row.market]
        .join(" ").toLowerCase().includes(needle))
      .sort((a, b) => (b.market_value_usd ?? 0) - (a.market_value_usd ?? 0));
  }, [snapshot, query, sourceFilter]);

  const brokerAllocation = useMemo(() => (snapshot?.accounts ?? [])
    .filter((row) => row.status !== "error" && (row.total_usd ?? 0) > 0)
    .map((row) => ({
      id: row.source_id ?? row.broker,
      name: row.label ?? row.broker.toUpperCase(),
      value: row.total_usd ?? 0,
      connector: row.broker,
    })), [snapshot]);

  const holdingAllocation = useMemo(() => {
    const rows = [...(snapshot?.combined_holdings ?? [])]
      .filter((row) => row.market_value_usd > 0)
      .sort((a, b) => b.market_value_usd - a.market_value_usd);
    const shown = rows.slice(0, 7).map((row) => ({ name: row.symbol, value: row.market_value_usd }));
    const other = rows.slice(7).reduce((sum, row) => sum + row.market_value_usd, 0);
    if (other > 0) shown.push({ name: zh ? "其他持仓" : "Other", value: other });
    const valuation = snapshot?.valuation;
    if ((valuation?.cash_usd ?? 0) > 0.01) shown.push({ name: zh ? "现金" : "Cash", value: valuation?.cash_usd ?? 0 });
    if ((valuation?.unpriced_or_other_usd ?? 0) > 0.01) shown.push({ name: zh ? "未定价/其他" : "Unpriced / other", value: valuation?.unpriced_or_other_usd ?? 0 });
    if (!valuation && snapshot) {
      const priced = rows.reduce((sum, row) => sum + row.market_value_usd, 0);
      const residual = Math.max(0, snapshot.totals.usd - priced);
      if (residual > 0.01) shown.push({ name: zh ? "现金/未定价" : "Cash / unpriced", value: residual });
    }
    return shown;
  }, [snapshot, zh]);

  const dailyChange = useMemo(() => {
    if (!snapshot || !history.length) return null;
    const sameDay = history.filter((row) => dayKey(row.created_at) === dayKey(snapshot.created_at));
    if (!sameDay.length) return null;
    return snapshot.totals.usd - Number(sameDay[0].total_usd);
  }, [snapshot, history]);

  const latestCompleteAt = history.length ? history[history.length - 1].created_at : undefined;
  const coverage = snapshot?.valuation?.identified_coverage ?? (() => {
    if (!snapshot?.totals.usd) return 0;
    return (snapshot.positions ?? []).reduce((sum, row) => sum + (row.priced ? row.market_value_usd : 0), 0) / snapshot.totals.usd;
  })();
  const displayCurrency = portfolioSettings?.display_currency ?? snapshot?.display_currency ?? "USD";
  const totalDisplay = displayCurrency === "CNY" ? snapshot?.totals.cny : snapshot?.totals.usd;

  return (
    <div className="min-h-screen p-4 sm:p-6 lg:p-8">
      <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6">
        <header className="flex flex-col gap-4 border-b pb-6 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs text-muted-foreground">
              <ShieldCheck className="h-3.5 w-3.5 text-positive" />
              {zh ? "本机只读 · 多账户汇总" : "Local read-only · Multi-account"}
            </div>
            <h1 className="text-3xl font-semibold tracking-tight">{zh ? "持仓总览" : "Portfolio"}</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {zh ? "统一汇总已启用的只读连接；连接失败时保留最后一次成功数据。" : "Unified valuation for enabled read-only connections with stale-safe fallback."}
            </p>
            {snapshot ? <p className="mt-2 text-xs text-muted-foreground">USD/CNY {snapshot.fx.usd_cny.toFixed(4)} · {snapshot.fx.stale ? (zh ? "缓存汇率" : "cached FX") : (zh ? "最新汇率" : "fresh FX")}</p> : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => setEditorOpen(true)} className="inline-flex items-center gap-2 rounded-md border bg-card px-4 py-2 text-sm">
              <Settings2 className="h-4 w-4" />{zh ? "管理账户" : "Manage accounts"}
            </button>
            <button onClick={() => void download()} disabled={!snapshot} className="inline-flex items-center gap-2 rounded-md border bg-card px-4 py-2 text-sm disabled:opacity-50">
              <Download className="h-4 w-4" /> CSV
            </button>
            <button onClick={() => void refresh()} disabled={refreshing || reconnecting} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
              {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {refreshing ? (zh ? "正在刷新" : "Refreshing") : (zh ? "刷新全部账户" : "Refresh all")}
            </button>
          </div>
        </header>

        {error ? <div className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger/5 p-4 text-sm text-danger"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div> : null}
        {refreshing && refreshState ? <RefreshProgress state={refreshState} settings={portfolioSettings} zh={zh} /> : null}
        {loading ? <div className="flex h-56 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div> : null}

        {!loading && !snapshot ? (
          <section className="rounded-xl border border-dashed p-12 text-center">
            <WalletCards className="mx-auto h-8 w-8 text-muted-foreground" />
            <h2 className="mt-4 font-medium">{zh ? "还没有持仓快照" : "No portfolio snapshot yet"}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{zh ? "添加至少一个只读账户后即可开始汇总。" : "Add at least one read-only account to begin."}</p>
            <button onClick={() => setEditorOpen(true)} className="mt-5 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"><Settings2 className="h-4 w-4" />{zh ? "添加账户" : "Add account"}</button>
          </section>
        ) : null}

        {snapshot ? (
          <>
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Metric label={zh ? "总资产" : "Total assets"} value={money(totalDisplay, displayCurrency)} note={displayCurrency === "USD" ? money(snapshot.totals.cny, "CNY") : money(snapshot.totals.usd)} icon={<WalletCards className="h-4 w-4" />} />
              <Metric label={zh ? "今日资产变化" : "Today's asset change"} value={dailyChange == null ? "—" : `${dailyChange >= 0 ? "+" : ""}${money(dailyChange)}`} note={zh ? "包含行情、入金和出金影响" : "Includes market moves and cash flows"} tone={dailyChange == null ? undefined : dailyChange >= 0 ? "positive" : "danger"} icon={<Clock3 className="h-4 w-4" />} />
              <Metric label={zh ? "估值覆盖率" : "Valuation coverage"} value={percentage(coverage)} note={zh ? `已定价 ${money(snapshot.valuation?.priced_usd)} · 现金 ${money(snapshot.valuation?.cash_usd)}` : "Priced holdings plus identified cash"} icon={<Database className="h-4 w-4" />} />
              <Metric label={zh ? "最后完整更新" : "Last complete update"} value={latestCompleteAt ? new Date(latestCompleteAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"} note={dateTime(latestCompleteAt)} tone={snapshot.complete ? "positive" : "warning"} icon={snapshot.complete ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />} />
            </section>

            <section className="grid gap-4 xl:grid-cols-2">
              <AllocationPie title={zh ? "按账户分布" : "Allocation by account"} data={brokerAllocation} centerLabel={money(totalDisplay, displayCurrency)} onSelect={(id) => setSourceFilter(id)} />
              <AllocationPie title={zh ? "按持仓标的分布" : "Allocation by holding"} data={holdingAllocation} centerLabel={zh ? "持仓占比" : "Holdings"} />
            </section>

            {snapshot.warnings.length ? (
              <section className="rounded-lg border border-warning/30 bg-warning/5 p-4 text-sm">
                <div className="mb-2 font-medium text-warning">{zh ? "数据说明" : "Data notes"}</div>
                <div className="space-y-1.5">{snapshot.warnings.map((warning) => <div key={warning} className="flex gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" /><span>{warning}</span></div>)}</div>
              </section>
            ) : null}

            <section>
              <div className="mb-3 flex items-end justify-between gap-3">
                <div><h2 className="font-semibold">{zh ? "账户状态" : "Account status"}</h2><p className="mt-1 text-xs text-muted-foreground">{zh ? "点击账户卡可筛选下方持仓" : "Click an account to filter holdings"}</p></div>
                {sourceFilter !== "all" ? <button className="text-xs text-primary" onClick={() => setSourceFilter("all")}>{zh ? "清除筛选" : "Clear filter"}</button> : null}
              </div>
              <div className="grid gap-3 lg:grid-cols-3">
                {snapshot.accounts.map((account) => (
                  <AccountCard key={account.source_id ?? account.broker} account={account} active={sourceFilter === (account.source_id ?? account.broker)} zh={zh} displayCurrency={displayCurrency} onClick={() => { const id = account.source_id ?? account.broker; setSourceFilter((current) => current === id ? "all" : id); }} onReconnect={account.auth?.method === "OAuth" && account.source_id ? () => void reconnectSource(account.source_id!) : undefined} reconnecting={reconnecting} />
                ))}
              </div>
            </section>

            <section className="overflow-hidden rounded-xl border bg-card">
              <div className="flex flex-col gap-3 border-b p-4 lg:flex-row lg:items-center lg:justify-between">
                <div><h2 className="font-semibold">{zh ? "持仓明细" : "Holdings"}</h2><p className="mt-1 text-xs text-muted-foreground">{positions.length} {zh ? "项持仓" : "positions"}</p></div>
                <div className="relative w-full lg:w-72"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "搜索账户、标的或市场" : "Search broker, symbol or market"} className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm" /></div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1050px] text-sm">
                  <thead className="bg-muted/40 text-left text-xs text-muted-foreground"><tr><Th>{zh ? "账户" : "Broker"}</Th><Th>{zh ? "标的" : "Symbol"}</Th><Th>{zh ? "类别" : "Type"}</Th><Th>{zh ? "数量" : "Quantity"}</Th><Th>{zh ? "成本 / 现价" : "Cost / Price"}</Th><Th>{zh ? "市值" : "Value"}</Th><Th>{zh ? "占比" : "Weight"}</Th><Th>{zh ? "未实现盈亏" : "Unrealized P/L"}</Th><Th>{zh ? "数据状态" : "Data"}</Th></tr></thead>
                  <tbody className="divide-y">
                    {positions.map((row) => {
                      const weight = snapshot.totals.usd > 0 ? row.market_value_usd / snapshot.totals.usd : 0;
                      return <tr key={`${row.source_id ?? row.broker}-${row.symbol}`} className="hover:bg-muted/20"><Td><div className="font-medium">{row.source_label ?? row.broker.toUpperCase()}</div><div className="mt-1 text-xs"><BrokerBadge broker={row.broker} /></div></Td><Td><div className="font-medium">{row.symbol}</div><div className="max-w-52 truncate text-xs text-muted-foreground">{row.name}</div></Td><Td><span className="capitalize text-muted-foreground">{row.asset_type}</span></Td><Td>{quantity(row.quantity)}</Td><Td><div>{price(row.cost_price)}</div><div className="text-xs text-muted-foreground">{price(row.market_price)}</div></Td><Td><div className="font-medium">{row.priced ? money(row.market_value_usd) : "—"}</div><div className="text-xs text-muted-foreground">{row.priced ? money(row.market_value_cny, "CNY") : "未定价"}</div></Td><Td>{row.priced ? percentage(weight) : "—"}</Td><Td><span className={row.unrealized_pnl_usd == null ? "text-muted-foreground" : row.unrealized_pnl_usd >= 0 ? "text-positive" : "text-danger"}>{row.unrealized_pnl_usd == null ? "—" : money(row.unrealized_pnl_usd)}</span></Td><Td><DataBadge stale={row.stale} priced={row.priced} zh={zh} /></Td></tr>;
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            <HistoryChart history={history} zh={zh} />

            <section className="rounded-xl border bg-card p-5">
              <div className="mb-4 flex items-center gap-2"><KeyRound className="h-4 w-4 text-muted-foreground" /><h2 className="font-semibold">{zh ? "连接与凭证" : "Connections and credentials"}</h2></div>
              <div className="grid gap-3 lg:grid-cols-3">{snapshot.accounts.map((account) => <CredentialCard key={account.source_id ?? account.broker} account={account} zh={zh} />)}</div>
            </section>
          </>
        ) : null}
      </div>
      <PortfolioSourceEditor open={editorOpen} settings={portfolioSettings} catalog={sourceCatalog} saving={savingSettings} zh={zh} onClose={() => setEditorOpen(false)} onSave={savePortfolioSettings} onConnectionsChanged={reloadConnections} />
    </div>
  );
}

function Metric({ label, value, note, icon, tone }: { label: string; value: string; note?: string; icon: ReactNode; tone?: "positive" | "danger" | "warning" }) {
  const toneClass = tone === "positive" ? "text-positive" : tone === "danger" ? "text-danger" : tone === "warning" ? "text-warning" : "";
  return <div className="rounded-xl border bg-card p-5"><div className="flex items-center justify-between text-xs text-muted-foreground"><span>{label}</span>{icon}</div><div className={`mt-3 text-2xl font-semibold tracking-tight ${toneClass}`}>{value}</div>{note ? <div className="mt-1 truncate text-xs text-muted-foreground" title={note}>{note}</div> : null}</div>;
}

function normalizeRefreshState(state: PortfolioRefreshState | null | undefined): PortfolioRefreshState {
  const candidate = state?.sources ?? state?.brokers;
  const sources = candidate && typeof candidate === "object" && !Array.isArray(candidate)
    ? Object.fromEntries(Object.entries(candidate).map(([sourceId, item]) => [
        sourceId,
        item && typeof item === "object" ? item : { status: "pending" as const },
      ]))
    : {};
  return {
    running: Boolean(state?.running),
    current: typeof state?.current === "string" ? state.current : null,
    sources,
    brokers: sources,
  };
}

function RefreshProgress({ state, settings, zh }: { state: PortfolioRefreshState; settings: PortfolioSettings | null; zh: boolean }) {
  const labels = new Map(settings?.sources.map((source) => [source.connection_id, source.label]) ?? []);
  const entries = Object.entries(normalizeRefreshState(state).sources ?? {});
  return <section className="rounded-lg border bg-card p-4"><div className="mb-3 flex items-center gap-2 text-sm font-medium"><Loader2 className="h-4 w-4 animate-spin text-primary" />{zh ? "正在依次读取已启用账户" : "Refreshing enabled accounts sequentially"}</div><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{entries.map(([sourceId, item]) => { const status = item.status ?? "pending"; return <div key={sourceId} className="flex items-center justify-between gap-3 rounded-md bg-muted/40 px-3 py-2 text-xs"><span className="truncate font-medium" title={labels.get(sourceId) ?? sourceId}>{labels.get(sourceId) ?? sourceId}</span><span className={status === "ok" ? "text-positive" : status === "error" ? "text-danger" : "text-muted-foreground"}>{status === "refreshing" ? (zh ? "读取中" : "Reading") : status === "ok" ? (zh ? "完成" : "Done") : status === "error" ? (zh ? "失败" : "Failed") : (zh ? "等待" : "Waiting")}</span></div>; })}</div></section>;
}

function AccountCard({ account, active, zh, displayCurrency, onClick, onReconnect, reconnecting }: { account: PortfolioAccount; active: boolean; zh: boolean; displayCurrency: "USD" | "CNY"; onClick: () => void; onReconnect?: () => void; reconnecting: boolean }) {
  const stale = account.status === "stale";
  const failed = account.status === "error";
  return <div role="button" tabIndex={0} onClick={onClick} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onClick(); }} className={`cursor-pointer rounded-xl border bg-card p-5 transition ${active ? "border-primary ring-1 ring-primary/20" : "hover:border-primary/40"}`}>
    <div className="flex items-center justify-between"><div><div className="font-medium">{account.label ?? account.broker.toUpperCase()}</div><div className="mt-1 text-xs"><BrokerBadge broker={account.broker} /></div></div>{failed ? <WifiOff className="h-4 w-4 text-danger" /> : stale ? <AlertTriangle className="h-4 w-4 text-warning" /> : <CheckCircle2 className="h-4 w-4 text-positive" />}</div>
    {failed ? <p className="mt-4 text-sm text-danger">{zh ? "连接失败，且没有可用缓存" : "Connection failed with no cache"}</p> : <><div className="mt-4 text-2xl font-semibold">{displayCurrency === "CNY" ? money(account.total_cny, "CNY") : money(account.total_usd)}</div><div className="mt-1 text-xs text-muted-foreground">{displayCurrency === "CNY" ? money(account.total_usd) : money(account.total_cny, "CNY")} · {account.position_count ?? 0} {zh ? "项持仓" : "positions"}</div><div className="mt-4 flex items-center justify-between border-t pt-3 text-xs"><span className={stale ? "text-warning" : "text-positive"}>{stale ? (zh ? "使用缓存" : "Cached") : (zh ? "数据正常" : "Fresh")}</span><span className="text-muted-foreground">{dateTime(account.last_success_at)}</span></div></>}
    {(failed || stale) && account.error ? <p className="mt-3 line-clamp-2 text-xs text-muted-foreground" title={account.error}>{account.error}</p> : null}
    {(failed || stale) && onReconnect ? <button onClick={(event) => { event.stopPropagation(); onReconnect(); }} disabled={reconnecting} className="mt-3 inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs disabled:opacity-50">{reconnecting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}{zh ? "重新连接" : "Reconnect"}</button> : null}
  </div>;
}

function BrokerBadge({ broker }: { broker: string }) {
  const color = BROKER_COLORS[broker.toUpperCase()] ?? "#7c8493";
  return <span className="inline-flex items-center gap-2 font-medium uppercase"><span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />{broker}</span>;
}

function DataBadge({ stale, priced, zh }: { stale?: boolean; priced: boolean; zh: boolean }) {
  if (stale) return <span className="rounded-full bg-warning/10 px-2 py-1 text-xs text-warning">{zh ? "缓存" : "Cached"}</span>;
  if (!priced) return <span className="rounded-full bg-muted px-2 py-1 text-xs text-muted-foreground">{zh ? "未定价" : "Unpriced"}</span>;
  return <span className="rounded-full bg-positive/10 px-2 py-1 text-xs text-positive">{zh ? "最新" : "Fresh"}</span>;
}

function CredentialCard({ account, zh }: { account: PortfolioAccount; zh: boolean }) {
  const auth = account.auth;
  const renewal = auth?.renewal === "automatic" ? (zh ? "连接器自动续期" : "Connector-managed renewal") : auth?.renewal === "session" ? (zh ? "依赖本地会话" : "Local session") : (zh ? "由服务商管理有效期" : "Provider-managed validity");
  return <div className="rounded-lg border p-4"><div className="flex items-center justify-between gap-3"><div><span className="font-medium">{account.label ?? account.broker.toUpperCase()}</span><div className="mt-1 text-xs text-muted-foreground">{account.broker.toUpperCase()}</div></div><span className={`shrink-0 rounded-full px-2 py-1 text-xs ${auth?.readonly ? "bg-positive/10 text-positive" : "bg-warning/10 text-warning"}`}>{auth?.readonly ? (zh ? "只读连接模板" : "Read-only profile") : (zh ? "连接模板可写" : "Write-capable profile")}</span></div><div className="mt-3 text-sm">{auth?.method ?? "—"} · {renewal}</div><p className="mt-1 text-xs text-muted-foreground">{auth?.detail ?? "—"}</p></div>;
}

type AllocationDatum = { id?: string; name: string; value: number; connector?: string };

function AllocationPie({ title, data, centerLabel, onSelect }: { title: string; data: AllocationDatum[]; centerLabel: string; onSelect?: (id: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || ref.current.clientWidth === 0) return;
    const chart = echarts.init(ref.current);
    const brokerPalette = data.map((item) => BROKER_COLORS[(item.connector ?? item.name).toUpperCase()]).filter(Boolean);
    const palette = brokerPalette.length === data.length ? brokerPalette : HOLDING_COLORS;
    chart.setOption({
      color: palette,
      tooltip: { trigger: "item", formatter: (params: { name: string; value: number; percent: number }) => `${params.name}<br/>${money(params.value)} · ${params.percent.toFixed(1)}%` },
      legend: { type: "scroll", bottom: 0, left: "center", textStyle: { color: "#7c8493" } },
      series: [{ type: "pie", radius: ["46%", "70%"], center: ["50%", "43%"], avoidLabelOverlap: true, padAngle: 2, itemStyle: { borderRadius: 5 }, label: { show: true, formatter: (params: { name: string; percent: number }) => params.percent >= 2 ? `${params.name}\n${params.percent.toFixed(1)}%` : "", fontSize: 12 }, labelLine: { length: 10, length2: 7 }, labelLayout: { hideOverlap: true }, data }],
      graphic: [{ type: "text", left: "center", top: "39%", style: { text: centerLabel, textAlign: "center", fill: "#7c8493", fontSize: 12, fontWeight: 600 } }],
    });
    const resize = () => chart.resize();
    const select = (params: { dataIndex?: number }) => { const item = params.dataIndex == null ? undefined : data[params.dataIndex]; if (item && onSelect) onSelect(item.id ?? item.name); };
    chart.on("click", select);
    window.addEventListener("resize", resize);
    return () => { window.removeEventListener("resize", resize); chart.off("click", select); chart.dispose(); };
  }, [data, centerLabel, onSelect]);
  return <div className="rounded-xl border bg-card p-5"><h2 className="font-semibold">{title}</h2><div ref={ref} className="h-80 w-full" /></div>;
}

function HistoryChart({ history, zh }: { history: PortfolioHistoryPoint[]; zh: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || ref.current.clientWidth === 0) return;
    const chart = echarts.init(ref.current);
    const rows = history.slice(-180);
    chart.setOption({
      grid: { left: 18, right: 18, top: 25, bottom: 28, containLabel: true },
      tooltip: { trigger: "axis", formatter: (items: Array<{ dataIndex: number; value: number }>) => { const item = items[0]; const row = rows[item.dataIndex]; return `${dateTime(row?.created_at)}<br/>${money(Number(item?.value))}`; } },
      xAxis: { type: "category", boundaryGap: false, data: rows.map((row) => new Date(row.created_at).toLocaleString([], { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })), axisLabel: { color: "#7c8493", hideOverlap: true }, axisLine: { lineStyle: { color: "#d6d9df" } } },
      yAxis: { type: "value", scale: true, axisLabel: { color: "#7c8493", formatter: (value: number) => `$${Math.round(value / 1000)}k` }, splitLine: { lineStyle: { color: "#d6d9df", opacity: 0.45 } } },
      series: [{ type: "line", data: rows.map((row) => Number(row.total_usd)), smooth: true, symbol: rows.length < 30 ? "circle" : "none", lineStyle: { width: 2, color: "#4f6edb" }, itemStyle: { color: "#4f6edb" }, areaStyle: { color: "rgba(79,110,219,0.10)" } }],
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => { window.removeEventListener("resize", resize); chart.dispose(); };
  }, [history]);
  return <section className="rounded-xl border bg-card p-5"><div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold">{zh ? "资产历史" : "Asset history"}</h2><p className="mt-1 text-xs text-muted-foreground">{zh ? "只显示完整快照；资产变化可能包含入金和出金。" : "Complete snapshots only; changes may include cash flows."}</p></div><span className="rounded-full bg-positive/10 px-2 py-1 text-xs text-positive">{history.length} {zh ? "个完整快照" : "complete snapshots"}</span></div>{history.length ? <div ref={ref} className="mt-4 h-64 w-full" /> : <div className="flex h-44 items-center justify-center text-sm text-muted-foreground">{zh ? "完成首次完整刷新后开始积累" : "History begins after a complete refresh"}</div>}</section>;
}

function Th({ children }: { children: ReactNode }) { return <th className="whitespace-nowrap px-4 py-3 font-medium">{children}</th>; }
function Td({ children }: { children: ReactNode }) { return <td className="px-4 py-3">{children}</td>; }
