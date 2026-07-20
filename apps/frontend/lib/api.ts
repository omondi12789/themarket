/**
 * Thin typed wrapper around the backend's REST API. Routes through Next's rewrite
 * (/api/backend/*) so the browser never needs the backend's raw URL / CORS setup
 * beyond what's configured in app/main.py.
 */

const BASE = "/api/backend";

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserOut {
  id: string;
  email: string;
  role: string;
  totp_enabled: boolean;
}

export const authApi = {
  register: (email: string, password: string) =>
    request<UserOut>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),

  login: (email: string, password: string, totp_code?: string) =>
    request<TokenPair>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, totp_code }),
    }),

  me: () => request<UserOut>("/auth/me"),

  refresh: (refresh_token: string) =>
    request<TokenPair>("/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token }) }),
};

export interface AccountSummary {
  id: string;
  broker_type: string;
  broker_login: string;
  is_live: boolean;
  balance: number;
  equity: number;
  currency: string;
}

export interface PositionSummary {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  volume: number;
  entry_price: number;
  unrealized_pnl: number;
}

export const tradingApi = {
  listAccounts: () => request<AccountSummary[]>("/accounts"),
  listPositions: (accountId: string) => request<PositionSummary[]>(`/accounts/${accountId}/positions`),
};

export interface OrderSummary {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  order_type: string;
  status: string;
  volume: number;
  broker_order_id: string | null;
}

export const ordersApi = {
  list: () => request<OrderSummary[]>("/orders"),
};

export interface Prediction {
  id: string;
  symbol: string;
  direction: "up" | "down";
  probability_up: number;
  confidence: number;
  model_type: string;
  cv_accuracy_mean: number;
  as_of: string;
  created_at: string;
  top_features?: Record<string, number> | null;
  model_breakdown?: { lightgbm_probability_up: number; xgboost_probability_up: number } | null;
}

export const predictionsApi = {
  list: (symbol?: string) => request<Prediction[]>(`/predictions${symbol ? `?symbol=${symbol}` : ""}`),
  generate: (symbol: string, timeframe = "1h") =>
    request<Prediction>("/predictions/generate", {
      method: "POST",
      body: JSON.stringify({ symbol, timeframe }),
    }),
  accuracy: (symbol?: string) =>
    request<{ evaluated_count: number; accuracy: number | null }>(
      `/predictions/accuracy${symbol ? `?symbol=${symbol}` : ""}`
    ),
};

export interface EquityPoint {
  captured_at: string;
  equity: number;
  balance: number;
}

export interface EquityHistoryResponse {
  account_id: string;
  points: EquityPoint[];
}

export interface PerformanceResponse {
  account_id: string;
  n_observations: number;
  metrics: {
    sharpe_ratio: number;
    sortino_ratio: number;
    calmar_ratio: number;
    max_drawdown: number;
    var_95: number;
    cvar_95: number;
    total_return: number;
    volatility_annualized: number;
  } | null;
  note?: string | null;
}

export const portfolioApi = {
  equityHistory: (days = 30) => request<EquityHistoryResponse[]>(`/portfolio/equity-history?days=${days}`),
  performance: (days = 30) => request<PerformanceResponse[]>(`/portfolio/performance?days=${days}`),
};

export interface ScanResult {
  symbol: string;
  signal: string;
  rsi_14: number | null;
  adx: number | null;
  price_vs_sma20_pct: number | null;
  bb_position: number | null;
  note?: string | null;
}

export const scannerApi = {
  scan: (symbols?: string, timeframe = "1h") =>
    request<ScanResult[]>(
      `/scanner/scan?timeframe=${timeframe}${symbols ? `&symbols=${symbols}` : ""}`
    ),
};

export interface SymbolExposure {
  symbol: string;
  net_volume: number;
  gross_volume: number;
  unrealized_pnl: number;
  position_count: number;
}

export interface AccountRiskSummary {
  account_id: string;
  is_live: boolean;
  equity: number;
  margin: number | null;
  free_margin: number | null;
  margin_utilization_pct: number | null;
  total_unrealized_pnl: number;
  open_position_count: number;
  exposures: SymbolExposure[];
}

export const riskApi = {
  summary: () => request<AccountRiskSummary[]>("/risk/summary"),
};

export interface RLSuggestion {
  id: string;
  symbol: string;
  suggested_size: number;
  action_index: number;
  confidence: number;
  agent_trained_at: string;
  created_at: string;
}

export const rlApi = {
  train: (symbol: string) =>
    request<{ training_summary: Record<string, number> }>("/rl/train", {
      method: "POST",
      body: JSON.stringify({ symbol }),
    }),
  suggestSize: (symbol: string) =>
    request<RLSuggestion>("/rl/suggest-size", {
      method: "POST",
      body: JSON.stringify({ symbol }),
    }),
};
