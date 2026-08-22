import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, FolderCode, Loader2, PlugZap, Plus, ShieldCheck, Trash2, X } from "lucide-react";
import { api, type ConnectionsResponse, type LocalConnection } from "@/lib/api";

interface Props {
  open: boolean;
  zh: boolean;
  onClose: () => void;
  onChanged: () => Promise<void>;
}

const fieldClass = "w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20";

export function ConnectionCenter({ open, zh, onClose, onChanged }: Props) {
  const [data, setData] = useState<ConnectionsResponse | null>(null);
  const [profileId, setProfileId] = useState("");
  const [connectionId, setConnectionId] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    setData(await api.getConnections());
  }

  useEffect(() => {
    if (!open) return;
    setMessage(null);
    void load().catch((error) => setMessage(error instanceof Error ? error.message : String(error)));
  }, [open]);

  const profiles = useMemo(() => data?.profiles.filter((profile) => !profile.invalid_plugin) ?? [], [data]);

  function chooseProfile(value: string) {
    setProfileId(value);
    const profile = profiles.find((item) => item.id === value);
    if (!profile) return;
    const ids = new Set(data?.connections.map((item) => item.id) ?? []);
    let id = `${profile.connector}-${profile.environment}`;
    let suffix = 2;
    while (ids.has(id)) id = `${profile.connector}-${profile.environment}-${suffix++}`;
    setConnectionId(id);
    setLabel(profile.label);
  }

  async function create() {
    if (!profileId || !connectionId.trim() || !label.trim()) return;
    setBusy("create");
    setMessage(null);
    try {
      await api.createConnection({ id: connectionId, profile_id: profileId, label });
      await load();
      await onChanged();
      setProfileId("");
      setConnectionId("");
      setLabel("");
      setMessage(zh ? "本地连接已创建。" : "Local connection created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  async function test(connection: LocalConnection) {
    setBusy(`test:${connection.id}`);
    setMessage(null);
    try {
      const result = await api.checkConnection(connection.id);
      const ok = result.report.status === "ok" || result.report.configured === true;
      setMessage(ok ? (zh ? `${connection.label} 连接正常。` : `${connection.label} is ready.`) : JSON.stringify(result.report));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  async function remove(connection: LocalConnection) {
    setBusy(`delete:${connection.id}`);
    setMessage(null);
    try {
      await api.deleteConnection(connection.id);
      await load();
      await onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  if (!open) return null;

  return <div className="fixed inset-0 z-[60] flex justify-end bg-black/40" role="presentation">
    <section className="flex h-full w-full max-w-2xl flex-col border-l bg-background shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="connection-center-title">
      <header className="flex items-start justify-between border-b p-5">
        <div><h2 id="connection-center-title" className="text-lg font-semibold">{zh ? "本地连接中心" : "Local connection center"}</h2><p className="mt-1 text-xs text-muted-foreground">{zh ? "连接定义保存在本机；密钥只进入系统钥匙串。" : "Definitions stay local; secrets go only to the OS credential vault."}</p></div>
        <button type="button" onClick={onClose} className="rounded-md p-2 hover:bg-muted" aria-label={zh ? "关闭连接中心" : "Close connection center"}><X className="h-4 w-4" /></button>
      </header>

      <div className="flex-1 space-y-6 overflow-y-auto p-5">
        {message ? <div className="rounded-md border bg-muted/30 p-3 text-xs break-words">{message}</div> : null}

        <section className="rounded-xl border bg-card p-4">
          <div className="flex items-center gap-2"><Plus className="h-4 w-4 text-primary" /><h3 className="font-medium">{zh ? "创建账户连接" : "Create account connection"}</h3></div>
          <p className="mt-1 text-xs text-muted-foreground">{zh ? "Profile 是公开模板；连接是只属于这台电脑的账户实例。" : "A profile is a public template; a connection is private to this computer."}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="text-xs text-muted-foreground sm:col-span-2">{zh ? "只读连接模板" : "Read-only profile"}<select value={profileId} onChange={(event) => chooseProfile(event.target.value)} className={`mt-1 ${fieldClass}`}><option value="">{zh ? "选择模板…" : "Choose a profile…"}</option>{profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.label}</option>)}</select></label>
            <label className="text-xs text-muted-foreground">{zh ? "本地连接 ID" : "Local connection ID"}<input value={connectionId} onChange={(event) => setConnectionId(event.target.value.toLowerCase())} className={`mt-1 ${fieldClass}`} placeholder="my-broker-live" /></label>
            <label className="text-xs text-muted-foreground">{zh ? "显示名称" : "Display name"}<input value={label} onChange={(event) => setLabel(event.target.value)} className={`mt-1 ${fieldClass}`} placeholder={zh ? "我的主账户" : "My main account"} /></label>
          </div>
          <button type="button" onClick={() => void create()} disabled={!profileId || busy === "create"} className="mt-3 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-40">{busy === "create" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}{zh ? "创建本地连接" : "Create connection"}</button>
        </section>

        <section>
          <div className="flex items-end justify-between"><div><h3 className="font-medium">{zh ? "这台电脑上的连接" : "Connections on this computer"}</h3><p className="mt-1 text-xs text-muted-foreground">{data?.connections.length ?? 0} {zh ? "个连接" : "connections"}</p></div><ShieldCheck className="h-5 w-5 text-positive" /></div>
          <div className="mt-3 space-y-3">{data?.connections.map((connection) => <ConnectionCard key={connection.id} connection={connection} zh={zh} busy={busy} onTest={test} onDelete={remove} onSaved={async () => { await load(); await onChanged(); }} setBusy={setBusy} setMessage={setMessage} />)}{data && !data.connections.length ? <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">{zh ? "还没有本地连接" : "No local connections yet"}</div> : null}</div>
        </section>

        <section className="rounded-xl border border-dashed p-4">
          <div className="flex items-center gap-2"><FolderCode className="h-4 w-4" /><h3 className="font-medium">{zh ? "让 Codex 接入新券商" : "Add a broker with Codex"}</h3></div>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">{zh ? "让 Codex 运行 connector init，根据券商官方文档补全只读 adapter，通过 validate 后 install。插件安装在下面的本机目录，不进入项目仓库。" : "Ask Codex to run connector init, implement the read adapter from official docs, validate it, then install it. The plugin stays outside the repository."}</p>
          <code className="mt-3 block overflow-x-auto rounded-md bg-muted p-3 text-xs">{data?.plugin_directory ?? "~/.vibe-trading/connectors"}</code>
        </section>
      </div>
    </section>
  </div>;
}

function ConnectionCard({ connection, zh, busy, onTest, onDelete, onSaved, setBusy, setMessage }: { connection: LocalConnection; zh: boolean; busy: string | null; onTest: (connection: LocalConnection) => Promise<void>; onDelete: (connection: LocalConnection) => Promise<void>; onSaved: () => Promise<void>; setBusy: (value: string | null) => void; setMessage: (value: string | null) => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  async function saveCredentials() {
    setBusy(`credentials:${connection.id}`);
    setMessage(null);
    try {
      await api.saveConnectionCredentials(connection.id, values);
      setValues({});
      await onSaved();
      setMessage(zh ? "凭证已保存到系统钥匙串。" : "Credentials saved to the OS vault.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }
  return <article className="rounded-xl border bg-card p-4">
    <div className="flex items-start justify-between gap-3"><div><div className="font-medium">{connection.label}</div><div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground"><span>{connection.connector.toUpperCase()}</span><span>·</span><span>{connection.environment === "live" ? (zh ? "实盘" : "Live") : (zh ? "模拟" : "Paper")}</span><span>·</span><span>{connection.transport}</span></div></div><span className="inline-flex items-center gap-1 rounded-full bg-positive/10 px-2 py-1 text-xs text-positive"><ShieldCheck className="h-3 w-3" />{zh ? "结构只读" : "Read-only"}</span></div>
    {connection.credential_fields.length ? <div className="mt-4 grid gap-2 sm:grid-cols-2">{connection.credential_fields.map((field) => <label key={field.name} className="text-xs text-muted-foreground">{field.label}{connection.credential_status[field.name] ? <span className="ml-1 text-positive">{zh ? "已保存" : "saved"}</span> : null}<input type={field.secret ? "password" : "text"} value={values[field.name] ?? ""} onChange={(event) => setValues((current) => ({ ...current, [field.name]: event.target.value }))} className={`mt-1 ${fieldClass}`} placeholder={connection.credential_status[field.name] ? "••••••••" : ""} autoComplete="off" /></label>)}</div> : <p className="mt-3 text-xs text-muted-foreground">{connection.transport === "remote_mcp" ? (zh ? "使用 OAuth；需要时通过重新连接完成授权。" : "Uses OAuth; authorize through reconnect when required.") : (zh ? "凭证由现有连接器本地配置管理。" : "Credentials are managed by the existing local connector configuration.")}</p>}
    <div className="mt-4 flex flex-wrap gap-2">{connection.credential_fields.length ? <button type="button" onClick={() => void saveCredentials()} disabled={busy === `credentials:${connection.id}` || !Object.values(values).some(Boolean)} className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs disabled:opacity-40"><ShieldCheck className="h-3.5 w-3.5" />{zh ? "保存到钥匙串" : "Save to vault"}</button> : null}<button type="button" onClick={() => void onTest(connection)} disabled={busy === `test:${connection.id}`} className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs">{busy === `test:${connection.id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlugZap className="h-3.5 w-3.5" />}{zh ? "测试连接" : "Test"}</button><button type="button" onClick={() => void onDelete(connection)} disabled={busy === `delete:${connection.id}`} className="ml-auto inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs text-danger hover:bg-danger/10"><Trash2 className="h-3.5 w-3.5" />{zh ? "删除" : "Delete"}</button></div>
    {connection.credentials_configured ? <div className="mt-3 flex items-center gap-1.5 text-xs text-positive"><CheckCircle2 className="h-3.5 w-3.5" />{zh ? "所需凭证已配置" : "Required credentials configured"}</div> : null}
  </article>;
}
