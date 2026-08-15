import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Portfolio } from "@/pages/Portfolio";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getPortfolio: vi.fn(),
      refreshPortfolio: vi.fn(),
      getPortfolioRefreshStatus: vi.fn(),
      reconnectPortfolioSource: vi.fn(),
      getPortfolioSettings: vi.fn(),
      updatePortfolioSettings: vi.fn(),
      getConnections: vi.fn(),
      createConnection: vi.fn(),
      saveConnectionCredentials: vi.fn(),
      checkConnection: vi.fn(),
      deleteConnection: vi.fn(),
      getPortfolioHistory: vi.fn(),
      downloadPortfolioCsv: vi.fn(),
    },
  };
});

const mocked = api as unknown as {
  getPortfolio: ReturnType<typeof vi.fn>;
  refreshPortfolio: ReturnType<typeof vi.fn>;
  getPortfolioRefreshStatus: ReturnType<typeof vi.fn>;
  reconnectPortfolioSource: ReturnType<typeof vi.fn>;
  getPortfolioSettings: ReturnType<typeof vi.fn>;
  updatePortfolioSettings: ReturnType<typeof vi.fn>;
  getConnections: ReturnType<typeof vi.fn>;
  createConnection: ReturnType<typeof vi.fn>;
  saveConnectionCredentials: ReturnType<typeof vi.fn>;
  checkConnection: ReturnType<typeof vi.fn>;
  deleteConnection: ReturnType<typeof vi.fn>;
  getPortfolioHistory: ReturnType<typeof vi.fn>;
  downloadPortfolioCsv: ReturnType<typeof vi.fn>;
};

const snapshot = {
  snapshot_id: "snap-1",
  created_at: "2026-08-09T00:00:00Z",
  complete: true,
  totals: { usd: 1000, cny: 7200 },
  valuation: { priced_usd: 800, cash_usd: 200, unpriced_or_other_usd: 0, identified_coverage: 1 },
  fx: { usd_cny: 7.2, usd_hkd: 7.8, fetched_at: "2026-08-09T00:00:00Z", stale: false },
  accounts: [
    { broker: "ibkr", status: "ok" as const, total_usd: 600, total_cny: 4320, position_count: 1, last_success_at: "2026-08-09T00:00:00Z" },
    { broker: "longbridge", status: "ok" as const, total_usd: 300, total_cny: 2160, position_count: 1, last_success_at: "2026-08-09T00:00:00Z" },
    { broker: "binance", status: "ok" as const, total_usd: 100, total_cny: 720, position_count: 1, last_success_at: "2026-08-09T00:00:00Z" },
  ],
  positions: [{
    broker: "ibkr", symbol: "AAPL", name: "Apple", asset_type: "stock", market: "US",
    currency: "USD", quantity: 2, cost_price: 100, market_price: 150,
    market_value_usd: 300, market_value_cny: 2160, unrealized_pnl_usd: 100,
    priced: true, updated_at: "2026-08-09T00:00:00Z",
  }],
  warnings: [],
};

const portfolioConfiguration = {
  status: "ok",
  settings: {
    display_currency: "USD" as const,
    sources: [
      { connection_id: "ibkr", label: "IBKR", enabled: true, order: 0, include_cash: true },
      { connection_id: "longbridge", label: "Longbridge", enabled: true, order: 1, include_cash: true },
      { connection_id: "binance", label: "Binance", enabled: true, order: 2, include_cash: true },
    ],
  },
  catalog: [
    { id: "ibkr", connection_id: "ibkr", profile_id: "ibkr-live-official-mcp-readonly", connector: "ibkr", label: "IBKR", environment: "live" as const, transport: "remote_mcp" as const, capabilities: ["mcp.read.discovery"], readonly: true, notes: "", selected: true, source_id: "ibkr", supports_reconnect: true, credential_fields: [], credential_status: {}, credentials_configured: false },
    { id: "longbridge", connection_id: "longbridge", profile_id: "longbridge-live-sdk-readonly", connector: "longbridge", label: "Longbridge", environment: "live" as const, transport: "broker_sdk" as const, capabilities: ["account.read", "positions.read"], readonly: true, notes: "", selected: true, source_id: "longbridge", supports_reconnect: false, credential_fields: [], credential_status: {}, credentials_configured: false },
    { id: "binance", connection_id: "binance", profile_id: "binance-live-sdk-readonly", connector: "binance", label: "Binance", environment: "live" as const, transport: "broker_sdk" as const, capabilities: ["account.read", "positions.read"], readonly: true, notes: "", selected: true, source_id: "binance", supports_reconnect: false, credential_fields: [], credential_status: {}, credentials_configured: false },
  ],
};

describe("Portfolio page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.getPortfolio.mockResolvedValue({ status: "ok", snapshot });
    mocked.getPortfolioHistory.mockResolvedValue({ status: "ok", history: [] });
    mocked.getPortfolioSettings.mockResolvedValue(portfolioConfiguration);
    mocked.updatePortfolioSettings.mockResolvedValue(portfolioConfiguration);
    mocked.refreshPortfolio.mockResolvedValue({ status: "ok", snapshot });
    mocked.getPortfolioRefreshStatus.mockResolvedValue({
      status: "ok",
      refresh: {
        running: false,
        current: null,
        sources: {
          ibkr: { status: "ok" },
          longbridge: { status: "ok" },
          binance: { status: "ok" },
        },
      },
    });
    mocked.getConnections.mockResolvedValue({
      status: "ok",
      connections: portfolioConfiguration.catalog,
      profiles: [{
        id: "sample-live-readonly",
        connector: "sample",
        label: "Sample Live · Local Read-Only",
        environment: "live",
        transport: "local_plugin",
        capabilities: ["account.read", "positions.read"],
        readonly: true,
        notes: "",
        local_plugin: true,
        credential_fields: [],
        supports_reconnect: false,
      }],
      plugin_directory: "/tmp/vibe/connectors",
    });
    mocked.createConnection.mockResolvedValue({ status: "ok", connection: {} });
  });

  it("renders the combined portfolio and refreshes all connectors", async () => {
    render(<Portfolio />);
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("$1,000.00")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Refresh all|刷新全部账户/ }));
    await waitFor(() => expect(mocked.refreshPortfolio).toHaveBeenCalledTimes(1));
  });

  it("keeps rendering when a legacy refresh response has a malformed source", async () => {
    let finishRefresh!: (value: { status: string; snapshot: typeof snapshot }) => void;
    mocked.refreshPortfolio.mockReturnValue(new Promise((resolve) => { finishRefresh = resolve; }));
    mocked.getPortfolioRefreshStatus.mockResolvedValue({
      status: "ok",
      refresh: {
        running: true,
        current: "ibkr",
        brokers: { ibkr: null },
      },
    });

    render(<Portfolio />);
    await screen.findByText("AAPL");
    fireEvent.click(screen.getByRole("button", { name: /Refresh all|刷新全部账户/ }));

    await waitFor(() => expect(mocked.getPortfolioRefreshStatus).toHaveBeenCalled(), { timeout: 2_000 });
    expect(screen.getByRole("heading", { name: /Portfolio|持仓总览/ })).toBeInTheDocument();

    finishRefresh({ status: "ok", snapshot });
    await waitFor(() => expect(mocked.getPortfolioHistory).toHaveBeenCalledTimes(2));
  });

  it("edits selected read-only accounts without collecting credentials", async () => {
    render(<Portfolio />);
    await screen.findByText("AAPL");

    fireEvent.click(screen.getByRole("button", { name: /Manage accounts|管理账户/ }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    const labels = screen.getAllByRole("textbox", { name: /Account label|账户名称/ });
    fireEvent.change(labels[0], { target: { value: "Main IBKR" } });
    fireEvent.click(screen.getByRole("button", { name: /Save and refresh|保存并刷新/ }));

    await waitFor(() => expect(mocked.updatePortfolioSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        sources: expect.arrayContaining([expect.objectContaining({ label: "Main IBKR" })]),
      }),
    ));
  });

  it("creates a computer-local connection from the connection center", async () => {
    render(<Portfolio />);
    await screen.findByText("AAPL");

    fireEvent.click(screen.getByRole("button", { name: /Manage accounts|管理账户/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Open connection center|打开连接中心/ }));
    fireEvent.change(await screen.findByLabelText(/Read-only profile|只读连接模板/), {
      target: { value: "sample-live-readonly" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Create connection|创建本地连接/ }));

    await waitFor(() => expect(mocked.createConnection).toHaveBeenCalledWith({
      id: "sample-live",
      profile_id: "sample-live-readonly",
      label: "Sample Live · Local Read-Only",
    }));
  });
});
