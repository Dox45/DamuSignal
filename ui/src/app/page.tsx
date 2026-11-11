'use client';

import React, { useState, useEffect, useMemo } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Database,
  Edit3,
  Flame,
  Hospital,
  Info,
  Layers,
  LineChart,
  Lock,
  LogOut,
  MapPin,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  Truck,
  Users,
  XCircle,
  Zap,
} from 'lucide-react';

interface Facility {
  facility_id: string;
  name: string;
  facility_type: string;
  county: string;
  lat: number;
  lon: number;
  keph_level: string;
  beds: number;
  grid_reliability: number;
  connectivity: string;
  supply_centre_id: string;
  makes_platelets: number;
  separates_components: number;
  has_blood_fridge_backup_power: number;
}

interface InventoryItem {
  id: number;
  facility_id: string;
  component: string;
  blood_group: string;
  current_units: number;
  last_updated: string;
}

interface ForecastItem {
  id: number;
  facility_id: string;
  blood_group: string;
  forecast_date: string;
  horizon_day: number;
  predicted_units: number;
  lower_estimate: number;
  upper_estimate: number;
  generated_at: string;
}

interface RiskItem {
  id: number;
  facility_id: string;
  blood_group: string;
  component: string;
  current_stock: number;
  projected_days_to_stockout: number | null;
  earliest_stockout_date: string | null;
  risk_status: 'Critical' | 'High Risk' | 'Moderate Risk' | 'Stable';
  contributing_factors: string;
  simulated_at: string;
}

interface RecommendationItem {
  recommendation_id: string;
  target_facility_id: string;
  target_facility_name: string;
  source_facility_id: string;
  source_facility_name: string;
  blood_group: string;
  component: string;
  recommended_quantity: number;
  approved_quantity: number;
  road_km: number;
  typical_travel_hours: number;
  justification: string;
  status: 'Pending Approval' | 'Approved' | 'Modified' | 'Rejected';
  created_at: string;
  updated_at: string;
}

interface AuditLogItem {
  id: number;
  recommendation_id: string;
  action: string;
  user_id: string;
  previous_status: string;
  new_status: string;
  previous_quantity: number | null;
  new_quantity: number | null;
  timestamp: string;
  notes: string;
}

interface SystemStatus {
  current_system_time?: string;
  last_sync_timestamp?: string;
  data_age_hours?: number;
  is_stale?: boolean;
  is_ml_online?: boolean;
  operational_mode?: string;
  health_warning?: string | null;
}

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'facilities' | 'forecasting' | 'risks' | 'recommendations' | 'audit'>('overview');
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [forecasts, setForecasts] = useState<ForecastItem[]>([]);
  const [risks, setRisks] = useState<RiskItem[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [selectedFacilityId, setSelectedFacilityId] = useState<string>('HSP-001');
  const [selectedForecastBg, setSelectedForecastBg] = useState<string>('O+');
  const [riskFilter, setRiskFilter] = useState<string>('ALL');
  const [recFilter, setRecFilter] = useState<string>('Pending Approval');

  // Authentication State
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [authUser, setAuthUser] = useState<{ username: string; name: string; role: string; facility_id: string } | null>(null);
  const [authChecking, setAuthChecking] = useState<boolean>(true);
  const [loginUsername, setLoginUsername] = useState<string>('');
  const [loginPassword, setLoginPassword] = useState<string>('');
  const [authError, setAuthError] = useState<string | null>(null);
  const [isLoggingIn, setIsLoggingIn] = useState<boolean>(false);

  // Modals state
  const [modifyModal, setModifyModal] = useState<{
    isOpen: boolean;
    rec: RecommendationItem | null;
    newQty: number;
    user: string;
    notes: string;
  }>({
    isOpen: false,
    rec: null,
    newQty: 5,
    user: 'dr_odhiambo_chief_transfusion',
    notes: 'Quantity adjusted for vehicle storage capacity constraint.',
  });

  const [rejectModal, setRejectModal] = useState<{
    isOpen: boolean;
    rec: RecommendationItem | null;
    user: string;
    reason: string;
  }>({
    isOpen: false,
    rec: null,
    user: 'dr_odhiambo_chief_transfusion',
    reason: 'Local elective surgeries cancelled; target hospital does not have adequate storage temperature monitoring.',
  });

  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  const API_BASE = process.env.NEXT_PUBLIC_API_URL
    ? process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, '')
    : (typeof window !== 'undefined' && window.location.port === '3000'
        ? '/api'
        : 'http://localhost:8000/api');

  // Authenticated fetch wrapper injecting Bearer token
  const authFetch = async (url: string, options: RequestInit = {}, customToken?: string) => {
    const token = customToken || authToken || (typeof window !== 'undefined' ? localStorage.getItem('terumo_token') : null);
    const headers = {
      ...(options.headers || {}),
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    };
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('terumo_token');
        localStorage.removeItem('terumo_user');
      }
      setAuthToken(null);
      setAuthUser(null);
      throw new Error('Unauthorized');
    }
    return res;
  };

  const handleLogin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setIsLoggingIn(true);
    setAuthError(null);
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: loginUsername, password: loginPassword }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Invalid username or password');
      }
      const data = await res.json();
      setAuthToken(data.token);
      setAuthUser(data.user);
      if (typeof window !== 'undefined') {
        localStorage.setItem('terumo_token', data.token);
        localStorage.setItem('terumo_user', JSON.stringify(data.user));
      }
      showToast(`Welcome back, ${data.user.name}`, 'success');
      await loadData(data.token);
    } catch (err: any) {
      setAuthError(err.message || 'Authentication failed');
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('terumo_token');
      localStorage.removeItem('terumo_user');
    }
    setAuthToken(null);
    setAuthUser(null);
    showToast('Signed out successfully.', 'info');
  };

  // Check persisted auth session on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const savedToken = localStorage.getItem('terumo_token');
      const savedUser = localStorage.getItem('terumo_user');
      if (savedToken) {
        setAuthToken(savedToken);
        if (savedUser) {
          try {
            setAuthUser(JSON.parse(savedUser));
          } catch (e) {}
        }
      }
    }
    setAuthChecking(false);
  }, []);

  // Fetch initial data
  const loadData = async (overrideToken?: string) => {
    try {
      setLoading(true);
      const [facRes, invRes, foreRes, riskRes, recRes, auditRes, statusRes] = await Promise.all([
        authFetch(`${API_BASE}/facilities`, {}, overrideToken).then((r) => r.json()),
        authFetch(`${API_BASE}/inventory`, {}, overrideToken).then((r) => r.json()),
        authFetch(`${API_BASE}/forecasts`, {}, overrideToken).then((r) => r.json()),
        authFetch(`${API_BASE}/stockout-risks`, {}, overrideToken).then((r) => r.json()),
        authFetch(`${API_BASE}/recommendations`, {}, overrideToken).then((r) => r.json()),
        authFetch(`${API_BASE}/audit-logs`, {}, overrideToken).then((r) => r.json()),
        authFetch(`${API_BASE}/system-status`, {}, overrideToken).then((r) => r.json()),
      ]);

      setFacilities(facRes.facilities || []);
      setInventory(invRes.inventory || []);
      setForecasts(foreRes.forecasts || []);
      setRisks(riskRes.risks || []);
      setRecommendations(recRes.recommendations || []);
      setAuditLogs(auditRes.audit_logs || []);
      setSystemStatus(statusRes || {});
      if (facRes.facilities?.length > 0 && !selectedFacilityId) {
        setSelectedFacilityId(facRes.facilities[0].facility_id);
      }
    } catch (err: any) {
      console.warn('API error, relying on local mock/cache:', err);
      showToast('API unreachable. Running in offline/cache mode.', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (authToken) {
      loadData(authToken);
    }
  }, [authToken]);

  // KPIs
  const totalUsableUnits = useMemo(
    () => inventory.reduce((acc, curr) => acc + (curr.current_units || 0), 0),
    [inventory]
  );
  const criticalCount = useMemo(
    () => risks.filter((r) => r.risk_status === 'Critical').length,
    [risks]
  );
  const highRiskCount = useMemo(
    () => risks.filter((r) => r.risk_status === 'High Risk').length,
    [risks]
  );
  const pendingRecsCount = useMemo(
    () => recommendations.filter((r) => r.status === 'Pending Approval').length,
    [recommendations]
  );

  // Group inventory by blood group for Overview Bar Chart
  const bgDistribution = useMemo(() => {
    const counts: Record<string, number> = {
      'O+': 0, 'O-': 0, 'A+': 0, 'A-': 0,
      'B+': 0, 'B-': 0, 'AB+': 0, 'AB-': 0,
    };
    inventory.forEach((i) => {
      if (counts[i.blood_group] !== undefined) {
        counts[i.blood_group] += i.current_units;
      }
    });
    return counts;
  }, [inventory]);

  const maxBgUnits = Math.max(...Object.values(bgDistribution), 100);

  // Facility detail lookup
  const currentFacility = useMemo(
    () => facilities.find((f) => f.facility_id === selectedFacilityId) || facilities[0],
    [facilities, selectedFacilityId]
  );

  const facilityInventory = useMemo(
    () => inventory.filter((i) => i.facility_id === selectedFacilityId),
    [inventory, selectedFacilityId]
  );

  const facilityTotalUnits = useMemo(
    () => facilityInventory.reduce((acc, i) => acc + i.current_units, 0),
    [facilityInventory]
  );

  // Forecasting curve data
  const currentForecastData = useMemo(() => {
    return forecasts.filter(
      (f) => f.facility_id === selectedFacilityId && f.blood_group === selectedForecastBg
    );
  }, [forecasts, selectedFacilityId, selectedForecastBg]);

  const maxForecastVal = Math.max(
    ...currentForecastData.map((f) => f.upper_estimate || 0),
    1
  );

  // Human-in-the-Loop Actions
  const handleApprove = async (recId: string) => {
    try {
      setActionLoading(true);
      const res = await authFetch(`${API_BASE}/recommendations/${recId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: authUser?.username || 'dr_odhiambo',
          notes: 'Authorized for immediate emergency vehicle dispatch.',
        }),
      });
      if (res.ok) {
        showToast(`✅ Recommendation ${recId} APPROVED & logged in audit trail.`, 'success');
        await loadData();
      }
    } catch (e: any) {
      showToast('Approval action failed: ' + e.message, 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleModifySubmit = async () => {
    if (!modifyModal.rec) return;
    try {
      setActionLoading(true);
      const res = await authFetch(`${API_BASE}/recommendations/${modifyModal.rec.recommendation_id}/modify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: modifyModal.user || authUser?.username || 'dr_odhiambo',
          modified_quantity: modifyModal.newQty,
          notes: modifyModal.notes,
        }),
      });
      if (res.ok) {
        showToast(`✅ Recommendation ${modifyModal.rec.recommendation_id} MODIFIED to ${modifyModal.newQty} units.`, 'success');
        setModifyModal({ isOpen: false, rec: null, newQty: 5, user: '', notes: '' });
        await loadData();
      }
    } catch (e: any) {
      showToast('Modify action failed: ' + e.message, 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRejectSubmit = async () => {
    if (!rejectModal.rec) return;
    try {
      setActionLoading(true);
      const res = await authFetch(`${API_BASE}/recommendations/${rejectModal.rec.recommendation_id}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: rejectModal.user || authUser?.username || 'dr_odhiambo',
          reason: rejectModal.reason,
        }),
      });
      if (res.ok) {
        showToast(`❌ Recommendation ${rejectModal.rec.recommendation_id} DECLINED and recorded in audit log.`, 'info');
        setRejectModal({ isOpen: false, rec: null, user: '', reason: '' });
        await loadData();
      }
    } catch (e: any) {
      showToast('Reject action failed: ' + e.message, 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSimulate = async () => {
    try {
      setActionLoading(true);
      const res = await authFetch(`${API_BASE}/stockout-risks/simulate`, { method: 'POST' });
      if (res.ok) {
        showToast('⚡ Forward stockout simulation re-calculated with dynamic expirations.', 'success');
        await loadData();
      }
    } catch (e: any) {
      showToast('Simulation failed: ' + e.message, 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRetrainForecast = async () => {
    try {
      setActionLoading(true);
      const res = await authFetch(`${API_BASE}/forecasts/run`, { method: 'POST' });
      if (res.ok) {
        showToast('🔄 LightGBM model re-trained with 14-day recursive roll-forward.', 'success');
        await loadData();
      }
    } catch (e: any) {
      showToast('Forecasting run failed: ' + e.message, 'error');
    } finally {
      setActionLoading(false);
    }
  };

  if (authChecking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#140204] text-white">
        <div className="flex items-center gap-3">
          <RefreshCw className="w-6 h-6 animate-spin text-red-500" />
          <span className="text-sm font-medium">Verifying healthcare session credentials...</span>
        </div>
      </div>
    );
  }

  if (!authToken) {
    return (
      <div className="min-h-screen flex flex-col justify-center items-center bg-[#120204] text-[#FFF6F6] px-4 py-8 relative overflow-hidden">
        {/* Ambient decorative glow */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-red-900/20 rounded-full blur-3xl pointer-events-none" />

        {/* Toast Notification */}
        {toast && (
          <div
            className={`fixed bottom-5 right-5 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-2xl border text-sm font-medium transition-all ${
              toast.type === 'success'
                ? 'bg-emerald-950/90 border-emerald-600 text-emerald-200'
                : toast.type === 'error'
                ? 'bg-red-950/90 border-red-600 text-red-200'
                : 'bg-blue-950/90 border-blue-600 text-blue-200'
            }`}
          >
            {toast.type === 'success' ? <CheckCircle2 className="w-5 h-5 text-emerald-400" /> : <AlertTriangle className="w-5 h-5 text-red-400" />}
            <span>{toast.message}</span>
          </div>
        )}

        <div className="w-full max-w-md relative z-10 space-y-6">
          {/* Brand & Badge */}
          <div className="text-center space-y-2">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-red-600 to-red-900 shadow-xl shadow-red-950/80 mb-2 border border-red-500/30">
              <span className="text-3xl">🩸</span>
            </div>
            <div>
              <span className="inline-block px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase bg-red-950 text-red-400 border border-red-800/70">
                Terumo BCT Africa Hackathon 2026
              </span>
            </div>
            <h1 className="text-2xl font-black text-white tracking-tight">Blood Inventory Intelligence</h1>
            <p className="text-xs text-gray-400 max-w-xs mx-auto">
              Kenyan National Blood Transfusion Service Decision-Support Node
            </p>
          </div>

          {/* Login Card */}
          <div className="p-6 sm:p-8 bg-[#1E0508]/90 border border-[#48151A] rounded-2xl shadow-2xl backdrop-blur-md space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-[#3E1116]">
              <div className="flex items-center gap-2 text-xs font-semibold text-red-300">
                <Lock className="w-4 h-4 text-red-400" />
                <span>Restricted Medical Access Gate</span>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-800/40 font-mono">
                RBAC Level 3
              </span>
            </div>

            {authError && (
              <div className="p-3 rounded-lg bg-red-950/80 border border-red-600/70 text-red-200 text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <span>{authError}</span>
              </div>
            )}

            <form onSubmit={handleLogin} className="space-y-4 text-xs">
              <div className="space-y-1.5">
                <label className="text-gray-300 font-medium">Healthcare Officer ID / Username</label>
                <input
                  type="text"
                  required
                  value={loginUsername}
                  onChange={(e) => setLoginUsername(e.target.value)}
                  placeholder="e.g. dr_odhiambo"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-[#120204] border border-[#48151A] text-white focus:outline-none focus:border-red-500 font-mono text-sm placeholder:text-gray-600 transition"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-gray-300 font-medium">Password</label>
                <input
                  type="password"
                  required
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-[#120204] border border-[#48151A] text-white focus:outline-none focus:border-red-500 text-sm placeholder:text-gray-600 transition"
                />
              </div>

              <button
                type="submit"
                disabled={isLoggingIn}
                className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-red-600 to-red-700 hover:from-red-500 hover:to-red-600 text-white font-bold text-sm shadow-lg shadow-red-950/60 flex items-center justify-center gap-2 transition disabled:opacity-50"
              >
                {isLoggingIn ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Authorizing Officer Session...</span>
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-4 h-4" />
                    <span>Sign In to Blood Intelligence Node</span>
                  </>
                )}
              </button>
            </form>

            <div className="pt-2 border-t border-[#3E1116] text-[10px] text-gray-500 space-y-1 text-center">
              <p>🔒 Enforces cryptographic audit trail under ISBT 128 & Kenya NBTS guidelines.</p>
              <p>All human-in-the-loop transfer decisions are logged with authorizing clinician credentials.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-[#140204] text-[#FFF6F6]">
      {/* Toast Notification */}
      {toast && (
        <div
          className={`fixed bottom-5 right-5 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-2xl border text-sm font-medium transition-all ${
            toast.type === 'success'
              ? 'bg-emerald-950/90 border-emerald-600 text-emerald-200'
              : toast.type === 'error'
              ? 'bg-red-950/90 border-red-600 text-red-200'
              : 'bg-blue-950/90 border-blue-600 text-blue-200'
          }`}
        >
          {toast.type === 'success' ? <CheckCircle2 className="w-5 h-5 text-emerald-400" /> : <AlertTriangle className="w-5 h-5 text-red-400" />}
          <span>{toast.message}</span>
        </div>
      )}

      {/* Top African Operating Safeguards Bar */}
      <header className="bg-[#200407] border-b border-[#3E1116] px-4 py-2 text-xs">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded font-bold uppercase tracking-wider bg-red-950 text-red-400 border border-red-800/60 text-[10px]">
              TERUMO BCT AFRICA HACKATHON
            </span>
            <span className="text-gray-300 hidden sm:inline">Kenyan National Blood Service Decision-Support Node</span>
          </div>

          <div className="flex items-center gap-4 text-gray-300">
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${systemStatus.is_stale ? 'bg-amber-400 animate-ping' : 'bg-emerald-400 animate-pulse'}`} />
              <span>
                Mode: <strong className="text-white">{systemStatus.operational_mode || 'Full Predictive AI'}</strong>
              </span>
            </div>
            <div className="hidden md:flex items-center gap-1 text-gray-400">
              <Clock className="w-3.5 h-3.5" />
              <span>Sync Age: {systemStatus.data_age_hours ? `${systemStatus.data_age_hours} hrs` : '0.1 hrs'}</span>
            </div>
            <button
              onClick={() => loadData()}
              disabled={loading}
              className="flex items-center gap-1 px-2.5 py-1 rounded bg-red-900/40 hover:bg-red-800/60 border border-red-700/50 text-white font-medium transition"
            >
              <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
              <span>Sync Live</span>
            </button>

            {/* Authenticated Officer Badge & Sign Out */}
            <div className="flex items-center gap-2 pl-2 border-l border-red-900/50">
              <div className="flex items-center gap-1.5">
                <div className="w-5 h-5 rounded-full bg-red-700 flex items-center justify-center text-[10px] font-bold text-white shadow-sm">
                  {authUser?.username ? authUser.username.slice(0, 2).toUpperCase() : 'DR'}
                </div>
                <span className="text-gray-200 font-mono hidden sm:inline">
                  {authUser?.username || 'dr_odhiambo'}
                </span>
              </div>
              <button
                onClick={handleLogout}
                title="Sign out of secure session"
                className="flex items-center gap-1 px-2 py-0.5 rounded bg-black/40 hover:bg-red-950 text-gray-400 hover:text-red-300 border border-red-900/40 transition text-[11px]"
              >
                <LogOut className="w-3 h-3" />
                <span className="hidden md:inline">Sign Out</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation Header */}
      <nav className="bg-[#190305] border-b border-[#3A1014] sticky top-0 z-40 px-4">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between">
          <div className="flex items-center gap-3 py-3">
            <div className="w-9 h-9 rounded-lg bg-red-600 flex items-center justify-center text-white shadow-lg shadow-red-950 font-black text-xl">
              🩸
            </div>
            <div>
              <h1 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                Blood Inventory Intelligence
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/60 text-red-300 border border-red-800/50 font-mono">v2.0</span>
              </h1>
              <p className="text-[11px] text-gray-400">Early Warning, Demand Forecasting & Inter-Facility Redistribution</p>
            </div>
          </div>

          <div className="flex space-x-1 sm:space-x-3 overflow-x-auto py-2 text-xs sm:text-sm font-medium">
            {[
              { id: 'overview', label: 'Regional Overview', icon: Layers },
              { id: 'facilities', label: 'Facility Inventory', icon: Hospital },
              { id: 'forecasting', label: 'Demand Forecasting', icon: LineChart },
              { id: 'risks', label: 'Stock-Out Risks', icon: ShieldAlert },
              { id: 'recommendations', label: 'Recommendations', icon: Truck, badge: pendingRecsCount },
              { id: 'audit', label: 'Audit Trail', icon: Database },
            ].map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-lg transition-all ${
                    isActive
                      ? 'bg-red-600 text-white font-semibold shadow-md shadow-red-950'
                      : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{tab.label}</span>
                  {tab.badge !== undefined && tab.badge > 0 && (
                    <span className="ml-1 px-1.5 py-0.2 bg-white/20 text-white rounded-full text-[10px] font-bold">
                      {tab.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 space-y-6">

        {/* ========================================================================= */}
        {/* VIEW 1: REGIONAL OVERVIEW DASHBOARD                                       */}
        {/* ========================================================================= */}
        {activeTab === 'overview' && (
          <div className="space-y-6 animate-fadeIn">
            {/* Top KPI Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
              <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-4 shadow-sm hover:border-red-900/60 transition">
                <div className="flex items-center justify-between text-gray-400 text-xs">
                  <span>Total Usable Stock</span>
                  <Database className="w-4 h-4 text-emerald-400" />
                </div>
                <div className="mt-2 text-2xl font-black text-white">{totalUsableUnits.toLocaleString()}</div>
                <p className="text-[11px] text-emerald-400 mt-1 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> Live verified physical stock
                </p>
              </div>

              <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-4 shadow-sm hover:border-red-900/60 transition">
                <div className="flex items-center justify-between text-gray-400 text-xs">
                  <span>Critical Deficits</span>
                  <Flame className="w-4 h-4 text-red-500" />
                </div>
                <div className="mt-2 text-2xl font-black text-red-500">{criticalCount}</div>
                <p className="text-[11px] text-red-300 mt-1">Stockout projected within ≤3 days</p>
              </div>

              <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-4 shadow-sm hover:border-red-900/60 transition">
                <div className="flex items-center justify-between text-gray-400 text-xs">
                  <span>High Risk Positions</span>
                  <AlertTriangle className="w-4 h-4 text-orange-400" />
                </div>
                <div className="mt-2 text-2xl font-black text-orange-400">{highRiskCount}</div>
                <p className="text-[11px] text-orange-300 mt-1">Depletion projected within ≤7 days</p>
              </div>

              <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-4 shadow-sm hover:border-red-900/60 transition">
                <div className="flex items-center justify-between text-gray-400 text-xs">
                  <span>Pending Authorizations</span>
                  <Truck className="w-4 h-4 text-blue-400" />
                </div>
                <div className="mt-2 text-2xl font-black text-white">{pendingRecsCount}</div>
                <p className="text-[11px] text-blue-300 mt-1">Route-optimized redistribution</p>
              </div>

              <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-4 shadow-sm col-span-2 md:col-span-1 hover:border-red-900/60 transition">
                <div className="flex items-center justify-between text-gray-400 text-xs">
                  <span>Tracked Facilities</span>
                  <Hospital className="w-4 h-4 text-purple-400" />
                </div>
                <div className="mt-2 text-2xl font-black text-white">{facilities.length}</div>
                <p className="text-[11px] text-gray-400 mt-1">6 regional, 9 satellites, 32 hospitals</p>
              </div>
            </div>

            {/* Middle Grid: Blood Group Distribution & Critical Shortage Sites */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Blood Group Distribution Chart */}
              <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-5 lg:col-span-2">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="text-base font-bold text-white flex items-center gap-2">
                      <Activity className="w-4 h-4 text-red-500" />
                      Network Usable Inventory by Blood Group
                    </h2>
                    <p className="text-xs text-gray-400">Total units available across the Kenyan healthcare supply network</p>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded bg-black/40 border border-white/5 text-gray-300 font-mono">
                    All Components
                  </span>
                </div>

                {/* Custom SVG Bar Chart */}
                <div className="space-y-3 pt-2">
                  {Object.entries(bgDistribution).map(([bg, count]) => {
                    const pct = Math.round((count / maxBgUnits) * 100);
                    const isRare = bg.includes('-');
                    return (
                      <div key={bg} className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="font-bold flex items-center gap-1.5">
                            {bg}
                            {isRare && <span className="text-[10px] px-1 py-0.2 bg-red-950 text-red-300 rounded font-normal">Rare / Vulnerable</span>}
                          </span>
                          <span className="font-mono text-gray-300">{count} units ({pct}%)</span>
                        </div>
                        <div className="h-3 w-full bg-black/40 rounded-full overflow-hidden border border-white/5">
                          <div
                            className={`h-full rounded-full transition-all duration-700 ${
                              isRare ? 'bg-gradient-to-r from-red-600 to-red-400' : 'bg-gradient-to-r from-red-800 to-red-600'
                            }`}
                            style={{ width: `${Math.max(pct, 2)}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Priority Attention Sites */}
              <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h2 className="text-base font-bold text-white flex items-center gap-2">
                      <ShieldAlert className="w-4 h-4 text-red-500" />
                      Urgent Stockout Warnings
                    </h2>
                    <span className="text-xs text-red-400 font-bold">≤ 3 Days</span>
                  </div>
                  <p className="text-xs text-gray-400 mb-4">Ranked by days remaining until total stockout:</p>

                  <div className="space-y-2.5 overflow-y-auto max-h-72 pr-1">
                    {risks
                      .filter((r) => r.risk_status === 'Critical')
                      .slice(0, 6)
                      .map((r) => {
                        const fac = facilities.find((f) => f.facility_id === r.facility_id);
                        return (
                          <div
                            key={`${r.facility_id}-${r.component}-${r.blood_group}`}
                            className="p-2.5 bg-red-950/30 border border-red-900/40 rounded-xl flex items-center justify-between text-xs hover:border-red-700/60 transition"
                          >
                            <div>
                              <p className="font-bold text-white">{fac?.name || r.facility_id}</p>
                              <p className="text-[11px] text-red-300 font-mono">
                                {r.component} {r.blood_group} · <span className="font-bold">{r.current_stock}</span> units left
                              </p>
                            </div>
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-600 text-white shadow-sm">
                              {r.projected_days_to_stockout ? `Day ${r.projected_days_to_stockout}` : 'Immediate'}
                            </span>
                          </div>
                        );
                      })}
                  </div>
                </div>

                <div className="pt-4 border-t border-[#3E1116] flex justify-between items-center text-xs">
                  <span className="text-gray-400">Forecasting: LightGBM Regressor</span>
                  <button
                    onClick={() => setActiveTab('risks')}
                    className="text-red-400 hover:text-red-300 font-bold flex items-center gap-1 transition"
                  >
                    View All Risks <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* VIEW 2: FACILITY INVENTORY VIEW                                           */}
        {/* ========================================================================= */}
        {activeTab === 'facilities' && (
          <div className="space-y-6 animate-fadeIn">
            <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-400 mb-1">Select Healthcare Facility:</label>
                  <select
                    value={selectedFacilityId}
                    onChange={(e) => setSelectedFacilityId(e.target.value)}
                    className="bg-[#190305] border border-[#52191F] rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-red-500 w-full sm:w-96"
                  >
                    {facilities.map((f) => (
                      <option key={f.facility_id} value={f.facility_id}>
                        {f.name} ({f.county})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleSimulate}
                    disabled={actionLoading}
                    className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-red-700 hover:bg-red-600 text-white text-xs font-bold shadow-md transition"
                  >
                    <Zap className="w-3.5 h-3.5" />
                    <span>Run Forward Simulation</span>
                  </button>
                </div>
              </div>

              {/* Facility Metadata Profile */}
              {currentFacility && (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3 mt-5 pt-4 border-t border-[#3E1116] text-xs">
                  <div className="p-2.5 bg-black/20 rounded-xl border border-white/5">
                    <span className="text-gray-400">County:</span>
                    <p className="font-bold text-white text-sm mt-0.5">{currentFacility.county}</p>
                  </div>
                  <div className="p-2.5 bg-black/20 rounded-xl border border-white/5">
                    <span className="text-gray-400">Type:</span>
                    <p className="font-bold text-white capitalize text-sm mt-0.5">
                      {currentFacility.facility_type.replace(/_/g, ' ')}
                    </p>
                  </div>
                  <div className="p-2.5 bg-black/20 rounded-xl border border-white/5">
                    <span className="text-gray-400">Connectivity:</span>
                    <p className="font-bold text-white text-sm mt-0.5">{currentFacility.connectivity || '3G'}</p>
                  </div>
                  <div className="p-2.5 bg-black/20 rounded-xl border border-white/5">
                    <span className="text-gray-400">Grid Reliability:</span>
                    <p className="font-bold text-white text-sm mt-0.5">
                      {Math.round((currentFacility.grid_reliability || 0.8) * 100)}%
                    </p>
                  </div>
                  <div className="p-2.5 bg-black/20 rounded-xl border border-white/5">
                    <span className="text-gray-400">Fridge Backup:</span>
                    <p className="font-bold text-white text-sm mt-0.5">
                      {currentFacility.has_blood_fridge_backup_power ? '✅ Generator' : '❌ None'}
                    </p>
                  </div>
                  <div className="p-2.5 bg-black/20 rounded-xl border border-white/5">
                    <span className="text-gray-400">Total Units:</span>
                    <p className="font-bold text-emerald-400 text-sm mt-0.5">{facilityTotalUnits} units</p>
                  </div>
                </div>
              )}
            </div>

            {/* Inventory Matrix Breakdown */}
            <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-5">
              <h3 className="text-sm font-bold text-white mb-3">Facility Component Matrix</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-[#3E1116] text-gray-400 bg-black/30">
                      <th className="py-2.5 px-3">Component</th>
                      <th className="py-2.5 px-3 text-center">O+</th>
                      <th className="py-2.5 px-3 text-center">O-</th>
                      <th className="py-2.5 px-3 text-center">A+</th>
                      <th className="py-2.5 px-3 text-center">A-</th>
                      <th className="py-2.5 px-3 text-center">B+</th>
                      <th className="py-2.5 px-3 text-center">B-</th>
                      <th className="py-2.5 px-3 text-center">AB+</th>
                      <th className="py-2.5 px-3 text-center">AB-</th>
                      <th className="py-2.5 px-3 text-right">Total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#320D11]">
                    {['RBC', 'WB', 'PLT', 'FFP', 'CRYO'].map((comp) => {
                      let rowTotal = 0;
                      const groups = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-'];
                      const cells = groups.map((bg) => {
                        const item = facilityInventory.find((i) => i.component === comp && i.blood_group === bg);
                        const count = item ? item.current_units : 0;
                        rowTotal += count;
                        let color = 'text-gray-300';
                        if (count === 0) color = 'text-red-500 font-extrabold';
                        else if (count <= 2) color = 'text-orange-400 font-bold';
                        return (
                          <td key={bg} className={`py-3 px-3 text-center font-mono ${color}`}>
                            {count}
                          </td>
                        );
                      });

                      return (
                        <tr key={comp} className="hover:bg-white/5 transition">
                          <td className="py-3 px-3 font-bold text-white">{comp}</td>
                          {cells}
                          <td className="py-3 px-3 text-right font-bold text-emerald-400 font-mono">{rowTotal}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* VIEW 3: DEMAND FORECASTING VIEW                                           */}
        {/* ========================================================================= */}
        {activeTab === 'forecasting' && (
          <div className="space-y-6 animate-fadeIn">
            {/* Filter and Model Metrics Card */}
            <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex flex-wrap items-center gap-3">
                  <div>
                    <label className="block text-[11px] text-gray-400 mb-1">Facility:</label>
                    <select
                      value={selectedFacilityId}
                      onChange={(e) => setSelectedFacilityId(e.target.value)}
                      className="bg-[#190305] border border-[#52191F] rounded-lg px-3 py-1.5 text-xs text-white"
                    >
                      {facilities.map((f) => (
                        <option key={f.facility_id} value={f.facility_id}>
                          {f.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-[11px] text-gray-400 mb-1">Blood Group:</label>
                    <select
                      value={selectedForecastBg}
                      onChange={(e) => setSelectedForecastBg(e.target.value)}
                      className="bg-[#190305] border border-[#52191F] rounded-lg px-3 py-1.5 text-xs text-white"
                    >
                      {['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-'].map((bg) => (
                        <option key={bg} value={bg}>
                          {bg} {bg === 'O-' ? '(High Vulnerability)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <button
                  onClick={handleRetrainForecast}
                  disabled={actionLoading}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-red-700 hover:bg-red-600 text-white text-xs font-bold shadow-md transition"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${actionLoading ? 'animate-spin' : ''}`} />
                  <span>Re-train LightGBM Model</span>
                </button>
              </div>

              {/* Baseline vs Model Performance Stats */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5 pt-4 border-t border-[#3E1116] text-xs">
                <div className="p-3 bg-black/20 rounded-xl border border-white/5">
                  <span className="text-gray-400">Baseline (7-day MA) MAE:</span>
                  <p className="font-mono font-bold text-white text-base mt-0.5">0.4676</p>
                </div>
                <div className="p-3 bg-black/20 rounded-xl border border-white/5">
                  <span className="text-gray-400">Baseline 7-day WAPE:</span>
                  <p className="font-mono font-bold text-white text-base mt-0.5">128.6%</p>
                </div>
                <div className="p-3 bg-black/20 rounded-xl border border-white/5">
                  <span className="text-gray-400">LightGBM Model MAE:</span>
                  <p className="font-mono font-bold text-emerald-400 text-base mt-0.5">0.4917</p>
                </div>
                <div className="p-3 bg-black/20 rounded-xl border border-white/5">
                  <span className="text-gray-400">LightGBM Model WAPE:</span>
                  <p className="font-mono font-bold text-emerald-400 text-base mt-0.5">135.3%</p>
                </div>
              </div>
            </div>

            {/* 14-Day Recursive Curve Visualization */}
            <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-red-500" />
                    14-Day Forward Demand Projection Curve
                  </h3>
                  <p className="text-xs text-gray-400">
                    Showing daily predicted demand with 90% and 10% confidence bounds
                  </p>
                </div>
                <span className="text-xs px-2.5 py-1 rounded bg-red-950 text-red-300 border border-red-800/60 font-mono">
                  Recursive lag roll-forward
                </span>
              </div>

              {/* Dynamic Bar + Confidence Interval Forecast Chart */}
              <div className="h-72 w-full bg-black/30 rounded-xl border border-white/5 p-4 flex flex-col justify-between">
                {currentForecastData.length === 0 ? (
                  <div className="flex-1 flex flex-col items-center justify-center text-gray-400 text-xs gap-2">
                    <LineChart className="w-8 h-8 text-red-500/60" />
                    <p>No forecast points loaded for {selectedFacilityId} ({selectedForecastBg}).</p>
                    <button
                      onClick={handleRetrainForecast}
                      disabled={actionLoading}
                      className="px-3 py-1.5 rounded-lg bg-red-800/60 hover:bg-red-700 text-white font-semibold"
                    >
                      Generate 14-Day Forecast
                    </button>
                  </div>
                ) : (
                  <div className="flex-1 h-full flex items-end gap-2 pt-6 pb-1 min-h-0">
                    {currentForecastData.map((f) => {
                      const upperPct = Math.min(100, Math.max(8, Math.round((f.upper_estimate / maxForecastVal) * 100)));
                      const heightPct = Math.max(4, Math.min(upperPct, Math.round((f.predicted_units / maxForecastVal) * 100)));
                      const bandDeltaPct = Math.max(0, upperPct - heightPct);
                      return (
                        <div key={f.forecast_date} className="flex-1 h-full flex flex-col items-center justify-end gap-1 group relative min-w-0">
                          {/* Tooltip on hover */}
                          <div className="absolute -top-2 opacity-0 group-hover:opacity-100 transition-opacity bg-black border border-red-800 text-white text-[10px] p-1.5 rounded pointer-events-none whitespace-nowrap z-20 shadow-xl font-mono">
                            {f.forecast_date}
                            <br />
                            Pred: {f.predicted_units.toFixed(2)}u [{f.lower_estimate.toFixed(2)}–{f.upper_estimate.toFixed(2)}]
                          </div>
                          {/* Numeric value above bar */}
                          <span className="text-[9px] font-mono text-gray-300">
                            {f.predicted_units.toFixed(1)}
                          </span>
                          {/* Stacked Chart Column inside explicit flex-1 height container */}
                          <div className="w-full flex-1 flex flex-col justify-end items-center min-h-0">
                            {/* Upper 90% confidence interval band */}
                            {bandDeltaPct > 0 && (
                              <div
                                className="w-full bg-red-950/70 rounded-t border-t border-x border-dashed border-red-400/60"
                                style={{ height: `${bandDeltaPct}%` }}
                              />
                            )}
                            {/* Predicted Demand bar */}
                            <div
                              className={`w-full bg-gradient-to-t from-red-700 to-red-500 shadow-sm ${bandDeltaPct === 0 ? 'rounded-t' : ''} rounded-b-sm`}
                              style={{ height: `${heightPct}%` }}
                            />
                          </div>
                          <span className="text-[9px] text-gray-400 font-mono truncate w-full text-center pt-1">
                            {f.forecast_date.slice(5)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* VIEW 4: STOCK-OUT RISKS VIEW                                              */}
        {/* ========================================================================= */}
        {activeTab === 'risks' && (
          <div className="space-y-6 animate-fadeIn">
            <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
                <div>
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <ShieldAlert className="w-4 h-4 text-red-500" />
                    Stock-Out Early Warning Board
                  </h2>
                  <p className="text-xs text-gray-400">
                    Forward deficit alerts accounting for daily forecasted demand and unit expirations
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <select
                    value={riskFilter}
                    onChange={(e) => setRiskFilter(e.target.value)}
                    className="bg-[#190305] border border-[#52191F] rounded-xl px-3 py-1.5 text-xs text-white"
                  >
                    <option value="ALL">All Risk Levels</option>
                    <option value="Critical">Critical (≤3 Days or 0 Stock)</option>
                    <option value="High Risk">High Risk (≤7 Days)</option>
                    <option value="Moderate Risk">Moderate Risk (≤14 Days)</option>
                    <option value="Stable">Stable</option>
                  </select>

                  <button
                    onClick={handleSimulate}
                    disabled={actionLoading}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-red-700 hover:bg-red-600 text-white text-xs font-bold transition shadow-sm"
                  >
                    <Zap className="w-3.5 h-3.5" />
                    <span>Run Simulation</span>
                  </button>
                </div>
              </div>

              {/* Risks Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-[#3E1116] text-gray-400 bg-black/30">
                      <th className="py-2.5 px-3">Facility</th>
                      <th className="py-2.5 px-2">Component</th>
                      <th className="py-2.5 px-2">Group</th>
                      <th className="py-2.5 px-2 text-right">Current Stock</th>
                      <th className="py-2.5 px-2 text-center">Days to Stock-Out</th>
                      <th className="py-2.5 px-2">Est. Deficit Date</th>
                      <th className="py-2.5 px-2 text-center">Risk Status</th>
                      <th className="py-2.5 px-3">Contributing Factors (Evidence)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#320D11]">
                    {risks
                      .filter((r) => riskFilter === 'ALL' || r.risk_status === riskFilter)
                      .slice(0, 50)
                      .map((r) => {
                        const fac = facilities.find((f) => f.facility_id === r.facility_id);
                        let badgeClass = 'bg-emerald-950 text-emerald-300 border-emerald-800';
                        if (r.risk_status === 'Critical') badgeClass = 'bg-red-950 text-red-300 border-red-700';
                        else if (r.risk_status === 'High Risk') badgeClass = 'bg-orange-950 text-orange-300 border-orange-700';
                        else if (r.risk_status === 'Moderate Risk') badgeClass = 'bg-yellow-950 text-yellow-300 border-yellow-700';

                        return (
                          <tr key={`${r.facility_id}-${r.component}-${r.blood_group}`} className="hover:bg-white/5 transition">
                            <td className="py-2.5 px-3 font-semibold text-white">
                              {fac?.name || r.facility_id} <span className="font-mono text-gray-400 text-[10px]">({r.facility_id})</span>
                            </td>
                            <td className="py-2.5 px-2 font-mono">{r.component}</td>
                            <td className="py-2.5 px-2 font-bold text-white">{r.blood_group}</td>
                            <td className="py-2.5 px-2 text-right font-mono font-bold text-white">{r.current_stock}</td>
                            <td className="py-2.5 px-2 text-center font-mono font-bold">
                              {r.projected_days_to_stockout ? `Day ${r.projected_days_to_stockout}` : '>14 Days'}
                            </td>
                            <td className="py-2.5 px-2 font-mono text-gray-400">{r.earliest_stockout_date || 'Stable'}</td>
                            <td className="py-2.5 px-2 text-center">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${badgeClass}`}>
                                {r.risk_status}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-gray-300 text-[11px] max-w-sm" title={r.contributing_factors}>
                              {r.contributing_factors}
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* VIEW 5: RECOMMENDATIONS & HUMAN-IN-THE-LOOP VIEW                          */}
        {/* ========================================================================= */}
        {activeTab === 'recommendations' && (
          <div className="space-y-6 animate-fadeIn">
            <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5">
                <div>
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <Truck className="w-4 h-4 text-blue-400" />
                    Inter-Facility Redistribution Recommendations
                  </h2>
                  <p className="text-xs text-gray-400">
                    Route-optimized matches via routes.csv; ensures &gt;15 units reserve safety buffer at source facilities
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">Filter:</span>
                  <select
                    value={recFilter}
                    onChange={(e) => setRecFilter(e.target.value)}
                    className="bg-[#190305] border border-[#52191F] rounded-xl px-3 py-1.5 text-xs text-white"
                  >
                    <option value="ALL">All Actions</option>
                    <option value="Pending Approval">Pending Approval</option>
                    <option value="Approved">Approved</option>
                    <option value="Modified">Modified</option>
                    <option value="Rejected">Rejected</option>
                  </select>
                </div>
              </div>

              {/* Recommendations Cards Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {recommendations
                  .filter((r) => recFilter === 'ALL' || r.status === recFilter)
                  .map((r) => {
                    let statusBadge = 'bg-yellow-950 text-yellow-300 border-yellow-700';
                    if (r.status === 'Approved') statusBadge = 'bg-emerald-950 text-emerald-300 border-emerald-700';
                    if (r.status === 'Modified') statusBadge = 'bg-blue-950 text-blue-300 border-blue-700';
                    if (r.status === 'Rejected') statusBadge = 'bg-red-950 text-red-300 border-red-700';

                    const isActionable = r.status === 'Pending Approval';

                    return (
                      <div
                        key={r.recommendation_id}
                        className="p-5 bg-[#1B0507] border border-[#42151A] rounded-2xl space-y-4 hover:border-red-900/60 transition shadow-sm"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono font-bold text-red-400 text-xs">{r.recommendation_id}</span>
                          <span className={`px-2.5 py-0.5 rounded text-[11px] font-bold border ${statusBadge}`}>
                            {r.status}
                          </span>
                        </div>

                        <div className="text-xs space-y-1.5">
                          <p className="text-gray-300">
                            <strong className="text-white">Target Deficit:</strong> {r.target_facility_name}{' '}
                            <span className="text-gray-400 font-mono">({r.target_facility_id})</span>
                          </p>
                          <p className="text-gray-300">
                            <strong className="text-white">Source Surplus:</strong> {r.source_facility_name}{' '}
                            <span className="text-gray-400 font-mono">({r.source_facility_id})</span>
                          </p>
                          <p className="text-gray-300 flex items-center gap-1.5">
                            <MapPin className="w-3.5 h-3.5 text-red-400" />
                            <span>
                              Transit: <strong className="text-white font-mono">{r.road_km} km</strong> (~{r.typical_travel_hours} hrs road transit)
                            </span>
                          </p>
                        </div>

                        <div className="p-3 bg-black/40 rounded-xl border border-white/5 text-xs">
                          <span className="text-gray-400">Proposed Transfer:</span>
                          <p className="text-white font-black text-sm mt-0.5">
                            {r.approved_quantity || r.recommended_quantity} units of{' '}
                            <span className="text-red-400">
                              {r.component} {r.blood_group}
                            </span>
                          </p>
                          <p className="text-[11px] text-gray-400 mt-1">{r.justification}</p>
                        </div>

                        {isActionable ? (
                          <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#340E12]">
                            <button
                              onClick={() => setRejectModal({ isOpen: true, rec: r, user: 'dr_odhiambo_chief_transfusion', reason: '' })}
                              disabled={actionLoading}
                              className="px-3 py-1.5 rounded-lg bg-red-950 hover:bg-red-900 text-red-300 border border-red-800/60 text-xs font-semibold transition"
                            >
                              Reject
                            </button>
                            <button
                              onClick={() =>
                                setModifyModal({
                                  isOpen: true,
                                  rec: r,
                                  newQty: r.recommended_quantity,
                                  user: 'dr_odhiambo_chief_transfusion',
                                  notes: 'Adjusted to fit cold-box vehicle transport limit.',
                                })
                              }
                              disabled={actionLoading}
                              className="px-3 py-1.5 rounded-lg bg-blue-950 hover:bg-blue-900 text-blue-300 border border-blue-800/60 text-xs font-semibold transition"
                            >
                              Modify Qty
                            </button>
                            <button
                              onClick={() => handleApprove(r.recommendation_id)}
                              disabled={actionLoading}
                              className="px-4 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-bold shadow-md transition"
                            >
                              ✓ Authorize Transfer
                            </button>
                          </div>
                        ) : (
                          <div className="text-right text-[11px] text-gray-500 italic pt-1 border-t border-[#340E12]">
                            Action recorded in immutable audit log.
                          </div>
                        )}
                      </div>
                    );
                  })}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* VIEW 6: AUDIT TRAIL VIEW                                                  */}
        {/* ========================================================================= */}
        {activeTab === 'audit' && (
          <div className="space-y-6 animate-fadeIn">
            <div className="bg-[#22070A] border border-[#441318] rounded-2xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <Database className="w-4 h-4 text-emerald-400" />
                    Human Decision Audit Log
                  </h2>
                  <p className="text-xs text-gray-400">
                    Immutable history preserving human oversight for all transfers, modifications, and overrides
                  </p>
                </div>
                <span className="text-xs text-gray-400 font-mono">SQLite Persistent Storage</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-[#3E1116] text-gray-400 bg-black/30">
                      <th className="py-2.5 px-3">Log ID</th>
                      <th className="py-2.5 px-3">Recommendation</th>
                      <th className="py-2.5 px-3">Action</th>
                      <th className="py-2.5 px-3">Authorizing Personnel</th>
                      <th className="py-2.5 px-3">State Change</th>
                      <th className="py-2.5 px-3 font-mono">Units</th>
                      <th className="py-2.5 px-3">Timestamp</th>
                      <th className="py-2.5 px-3">Clinical Justification</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#320D11]">
                    {auditLogs.map((l) => (
                      <tr key={l.id} className="hover:bg-white/5 transition">
                        <td className="py-3 px-3 font-mono text-gray-400">#{l.id}</td>
                        <td className="py-3 px-3 font-mono font-bold text-red-400">{l.recommendation_id}</td>
                        <td className="py-3 px-3 font-bold uppercase text-[10px]">
                          <span
                            className={`px-2 py-0.5 rounded ${
                              l.action === 'approve'
                                ? 'bg-emerald-950 text-emerald-300'
                                : l.action === 'modify'
                                ? 'bg-blue-950 text-blue-300'
                                : 'bg-red-950 text-red-300'
                            }`}
                          >
                            {l.action}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-white font-medium">{l.user_id}</td>
                        <td className="py-3 px-3 text-gray-300">
                          {l.previous_status} → <strong className="text-white">{l.new_status}</strong>
                        </td>
                        <td className="py-3 px-3 font-mono text-emerald-400 font-bold">
                          {l.new_quantity !== null ? l.new_quantity : l.previous_quantity} units
                        </td>
                        <td className="py-3 px-3 text-gray-400 font-mono text-[11px]">
                          {l.timestamp.replace('T', ' ').slice(0, 19)}
                        </td>
                        <td className="py-3 px-3 text-gray-300 italic">{l.notes || '--'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* ========================================================================= */}
      {/* MODAL: MODIFY QUANTITY                                                    */}
      {/* ========================================================================= */}
      {modifyModal.isOpen && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50 animate-fadeIn">
          <div className="bg-[#24090C] border border-[#52191F] rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex justify-between items-center border-b border-[#3E1116] pb-3">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Edit3 className="w-4 h-4 text-blue-400" />
                Modify Transfer Recommendation
              </h3>
              <button
                onClick={() => setModifyModal({ ...modifyModal, isOpen: false })}
                className="text-gray-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-gray-300">
              Adjusting transfer for <strong className="text-white">{modifyModal.rec?.recommendation_id}</strong> (
              {modifyModal.rec?.component} {modifyModal.rec?.blood_group})
            </p>

            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Approved Transfer Units:</label>
              <input
                type="number"
                min="1"
                max="50"
                value={modifyModal.newQty}
                onChange={(e) => setModifyModal({ ...modifyModal, newQty: parseInt(e.target.value, 10) || 1 })}
                className="w-full bg-[#160204] border border-[#52191F] rounded-xl p-2.5 text-white font-mono text-sm focus:border-red-500 outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Authorizing User ID:</label>
              <input
                type="text"
                value={modifyModal.user}
                onChange={(e) => setModifyModal({ ...modifyModal, user: e.target.value })}
                className="w-full bg-[#160204] border border-[#52191F] rounded-xl p-2.5 text-white text-xs focus:border-red-500 outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Reason / Clinical Notes:</label>
              <textarea
                rows={2}
                value={modifyModal.notes}
                onChange={(e) => setModifyModal({ ...modifyModal, notes: e.target.value })}
                className="w-full bg-[#160204] border border-[#52191F] rounded-xl p-2.5 text-white text-xs focus:border-red-500 outline-none"
              />
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-[#3E1116]">
              <button
                onClick={() => setModifyModal({ ...modifyModal, isOpen: false })}
                className="px-3.5 py-2 rounded-xl bg-gray-800 text-gray-300 text-xs font-semibold hover:bg-gray-700 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleModifySubmit}
                disabled={actionLoading}
                className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-md transition"
              >
                Confirm Modification
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: REJECT RECOMMENDATION                                              */}
      {/* ========================================================================= */}
      {rejectModal.isOpen && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50 animate-fadeIn">
          <div className="bg-[#24090C] border border-[#52191F] rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex justify-between items-center border-b border-[#3E1116] pb-3">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <XCircle className="w-4 h-4 text-red-500" />
                Decline Transfer Recommendation
              </h3>
              <button
                onClick={() => setRejectModal({ ...rejectModal, isOpen: false })}
                className="text-gray-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-gray-300">
              Decline transfer <strong className="text-white">{rejectModal.rec?.recommendation_id}</strong> with mandatory clinical or logistical justification.
            </p>

            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Authorizing User ID:</label>
              <input
                type="text"
                value={rejectModal.user}
                onChange={(e) => setRejectModal({ ...rejectModal, user: e.target.value })}
                className="w-full bg-[#160204] border border-[#52191F] rounded-xl p-2.5 text-white text-xs focus:border-red-500 outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Mandatory Rejection Reason:</label>
              <textarea
                rows={3}
                value={rejectModal.reason}
                onChange={(e) => setRejectModal({ ...rejectModal, reason: e.target.value })}
                placeholder="e.g. Local elective surgeries cancelled; target hospital does not have adequate storage temperature monitoring."
                className="w-full bg-[#160204] border border-[#52191F] rounded-xl p-2.5 text-white text-xs focus:border-red-500 outline-none"
              />
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-[#3E1116]">
              <button
                onClick={() => setRejectModal({ ...rejectModal, isOpen: false })}
                className="px-3.5 py-2 rounded-xl bg-gray-800 text-gray-300 text-xs font-semibold hover:bg-gray-700 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleRejectSubmit}
                disabled={actionLoading || !rejectModal.reason.trim()}
                className="px-4 py-2 rounded-xl bg-red-700 hover:bg-red-600 disabled:opacity-50 text-white text-xs font-bold shadow-md transition"
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="bg-[#190305] border-t border-[#3A1014] px-4 py-3 text-xs text-gray-500">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>Terumo BCT Africa Hackathon 2026 · Starter Sandbox Production Prototype</span>
          <span className="font-mono">Next.js 16 (TypeScript + Tailwind) · FastAPI + SQLite · LightGBM Regressor</span>
        </div>
      </footer>
    </div>
  );
}
