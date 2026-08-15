import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Plus, Save, Trash2, X } from "lucide-react";
import { ConnectionCenter } from "@/components/portfolio/ConnectionCenter";
import type {
  PortfolioSettings,
  PortfolioSourceCatalogItem,
  PortfolioSourceSettings,
} from "@/lib/api";

interface Props {
  open: boolean;
  settings: PortfolioSettings | null;
  catalog: PortfolioSourceCatalogItem[];
  saving: boolean;
  zh: boolean;
  onClose: () => void;
  onSave: (settings: PortfolioSettings) => Promise<void>;
  onConnectionsChanged: () => Promise<void>;
}

const fieldClass = "w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20";

export function PortfolioSourceEditor({ open, settings, catalog, saving, zh, onClose, onSave, onConnectionsChanged }: Props) {
  const [draft, setDraft] = useState<PortfolioSettings | null>(settings);
  const [connectionToAdd, setConnectionToAdd] = useState("");
  const [connectionCenterOpen, setConnectionCenterOpen] = useState(false);

  useEffect(() => {
    if (open && settings) {
      setDraft({ ...settings, sources: settings.sources.map((source) => ({ ...source })) });
    }
  }, [open, settings]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open, onClose]);

  const available = useMemo(() => {
    const selected = new Set(draft?.sources.map((source) => source.connection_id) ?? []);
    return catalog.filter((item) => !selected.has(item.connection_id));
  }, [catalog, draft]);

  if (!open || !draft) return null;

  const updateSource = (index: number, update: Partial<PortfolioSourceSettings>) => {
    setDraft((current) => current && ({
      ...current,
      sources: current.sources.map((source, sourceIndex) => sourceIndex === index ? { ...source, ...update } : source),
    }));
  };

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= draft.sources.length) return;
    const sources = [...draft.sources];
    [sources[index], sources[target]] = [sources[target], sources[index]];
    setDraft({ ...draft, sources: sources.map((source, order) => ({ ...source, order })) });
  };

  const remove = (index: number) => {
    setDraft({
      ...draft,
      sources: draft.sources.filter((_, sourceIndex) => sourceIndex !== index)
        .map((source, order) => ({ ...source, order })),
    });
  };

  const add = () => {
    const connection = available.find((item) => item.connection_id === connectionToAdd) ?? available[0];
    if (!connection) return;
    setDraft({
      ...draft,
      sources: [...draft.sources, {
        connection_id: connection.connection_id,
        label: connection.label,
        enabled: true,
        order: draft.sources.length,
        include_cash: true,
      }],
    });
    setConnectionToAdd("");
  };

  return <div className="fixed inset-0 z-50 flex justify-end bg-black/35" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="flex h-full w-full max-w-xl flex-col border-l bg-background shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="portfolio-source-editor-title">
      <header className="flex items-start justify-between border-b p-5">
        <div><h2 id="portfolio-source-editor-title" className="text-lg font-semibold">{zh ? "管理持仓账户" : "Manage portfolio accounts"}</h2><p className="mt-1 text-xs text-muted-foreground">{zh ? "这里只保存账户选择和显示偏好，不保存密钥。" : "Only account selection and display preferences are stored here."}</p></div>
        <button type="button" onClick={onClose} className="rounded-md p-2 hover:bg-muted" aria-label={zh ? "关闭" : "Close"}><X className="h-4 w-4" /></button>
      </header>

      <div className="flex-1 space-y-6 overflow-y-auto p-5">
        <fieldset><legend className="text-sm font-medium">{zh ? "主要显示货币" : "Primary display currency"}</legend><div className="mt-2 grid grid-cols-2 gap-2">{(["USD", "CNY"] as const).map((currency) => <button key={currency} type="button" onClick={() => setDraft({ ...draft, display_currency: currency })} className={`rounded-md border px-3 py-2 text-sm ${draft.display_currency === currency ? "border-primary bg-primary/5 text-primary" : "bg-card"}`}>{currency}</button>)}</div></fieldset>

        <section>
          <div className="flex items-end justify-between gap-3"><div><h3 className="text-sm font-medium">{zh ? "已添加账户" : "Selected accounts"}</h3><p className="mt-1 text-xs text-muted-foreground">{zh ? "拖动顺序的替代操作：使用上下箭头。" : "Use the arrow buttons to change display order."}</p></div><span className="text-xs text-muted-foreground">{draft.sources.length}</span></div>
          <div className="mt-3 space-y-3">
            {draft.sources.map((source, index) => {
              const connection = catalog.find((item) => item.connection_id === source.connection_id);
              return <article key={source.connection_id} className="rounded-lg border bg-card p-4">
                <div className="flex items-start gap-3">
                  <input type="checkbox" checked={source.enabled} onChange={(event) => updateSource(index, { enabled: event.target.checked })} className="mt-2 h-4 w-4 accent-primary" aria-label={zh ? "启用账户" : "Enable account"} />
                  <div className="min-w-0 flex-1"><input value={source.label} onChange={(event) => updateSource(index, { label: event.target.value })} className={fieldClass} aria-label={zh ? "账户名称" : "Account label"} /><div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground"><span>{connection?.connector.toUpperCase()}</span><span>·</span><span>{connection?.environment === "live" ? (zh ? "实盘" : "Live") : (zh ? "模拟" : "Paper")}</span><span>·</span><span>{connection?.transport}</span></div></div>
                  <div className="flex gap-1"><button type="button" onClick={() => move(index, -1)} disabled={index === 0} className="rounded p-1.5 hover:bg-muted disabled:opacity-30" aria-label={zh ? "上移" : "Move up"}><ArrowUp className="h-4 w-4" /></button><button type="button" onClick={() => move(index, 1)} disabled={index === draft.sources.length - 1} className="rounded p-1.5 hover:bg-muted disabled:opacity-30" aria-label={zh ? "下移" : "Move down"}><ArrowDown className="h-4 w-4" /></button><button type="button" onClick={() => remove(index)} className="rounded p-1.5 text-danger hover:bg-danger/10" aria-label={zh ? "删除账户" : "Remove account"}><Trash2 className="h-4 w-4" /></button></div>
                </div>
                <label className="mt-3 flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={source.include_cash} onChange={(event) => updateSource(index, { include_cash: event.target.checked })} className="h-4 w-4 accent-primary" />{zh ? "计入该账户现金" : "Include this account's cash"}</label>
              </article>;
            })}
            {!draft.sources.length ? <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">{zh ? "还没有添加账户" : "No accounts selected"}</div> : null}
          </div>
        </section>

        <section><div className="flex items-end justify-between gap-3"><div><h3 className="text-sm font-medium">{zh ? "添加本地只读连接" : "Add a local read-only connection"}</h3><p className="mt-1 text-xs text-muted-foreground">{zh ? "这里只选择已经在这台电脑上创建的连接。" : "Choose from connections already created on this computer."}</p></div><button type="button" onClick={() => setConnectionCenterOpen(true)} className="shrink-0 text-xs text-primary">{zh ? "打开连接中心" : "Open connection center"}</button></div><div className="mt-3 flex gap-2"><select value={connectionToAdd} onChange={(event) => setConnectionToAdd(event.target.value)} className={fieldClass} disabled={!available.length}><option value="">{available.length ? (zh ? "选择连接…" : "Choose a connection…") : (zh ? "没有可添加的连接" : "No available connections")}</option>{available.map((connection) => <option key={connection.connection_id} value={connection.connection_id}>{connection.label}</option>)}</select><button type="button" onClick={add} disabled={!available.length} className="inline-flex shrink-0 items-center gap-2 rounded-md border px-3 py-2 text-sm disabled:opacity-40"><Plus className="h-4 w-4" />{zh ? "添加" : "Add"}</button></div></section>
      </div>

      <footer className="flex items-center justify-between gap-3 border-t p-5"><p className="text-xs text-muted-foreground">{zh ? "保存后将刷新已启用账户。" : "Enabled accounts refresh after saving."}</p><div className="flex gap-2"><button type="button" onClick={onClose} className="rounded-md border px-4 py-2 text-sm">{zh ? "取消" : "Cancel"}</button><button type="button" disabled={saving} onClick={() => void onSave({ ...draft, sources: draft.sources.map((source, order) => ({ ...source, order })) })} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"><Save className="h-4 w-4" />{saving ? (zh ? "保存中" : "Saving") : (zh ? "保存并刷新" : "Save and refresh")}</button></div></footer>
    </section>
    <ConnectionCenter open={connectionCenterOpen} zh={zh} onClose={() => setConnectionCenterOpen(false)} onChanged={onConnectionsChanged} />
  </div>;
}
