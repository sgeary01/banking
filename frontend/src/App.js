import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Accounts from './pages/Accounts';
import Transactions from './pages/Transactions';
import FraudAlerts from './pages/FraudAlerts';
import ChaosPanel from './pages/ChaosPanel';
import { listCustomers, login as apiLogin } from './services/api';

const NAV = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/accounts', label: 'Accounts' },
  { to: '/transactions', label: 'Transactions' },
  { to: '/fraud', label: 'Fraud Alerts' },
  { to: '/chaos', label: 'Chaos Panel' },
];

const styles = {
  nav: { background: '#1a1a2e', color: '#fff', display: 'flex', alignItems: 'center', padding: '0 24px', height: 56, gap: 8 },
  logo: { fontWeight: 700, fontSize: 18, marginRight: 24, color: '#1E40AF', letterSpacing: 1 },
  link: { color: '#ccc', textDecoration: 'none', padding: '6px 14px', borderRadius: 6, fontSize: 14 },
  activeLink: { color: '#fff', background: '#1E40AF' },
  logout: { marginLeft: 'auto', background: 'transparent', border: '1px solid #444', color: '#ccc', padding: '5px 14px', borderRadius: 6, cursor: 'pointer', fontSize: 14 },
};

function NavBar({ onLogout }) {
  return (
    <nav style={styles.nav}>
      <span style={styles.logo}>Atlas Financial</span>
      {NAV.map(n => (
        <NavLink key={n.to} to={n.to} style={({ isActive }) => ({ ...styles.link, ...(isActive ? styles.activeLink : {}) })}>
          {n.label}
        </NavLink>
      ))}
      <button style={styles.logout} onClick={onLogout}>Logout</button>
    </nav>
  );
}

// Demo mode: app auto-authenticates as the first seeded member on load.
// This avoids needing to know any credentials. Toggle by setting
// REACT_APP_AUTO_LOGIN=false at build time to fall back to the manual form.
const AUTO_LOGIN = (process.env.REACT_APP_AUTO_LOGIN || 'true') !== 'false';
const DEMO_PASSWORD = 'password123';

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [customerId, setCustomerId] = useState(localStorage.getItem('customerId'));
  const [autoLoginError, setAutoLoginError] = useState(null);

  const handleLogin = (tok, custId) => {
    localStorage.setItem('token', tok);
    localStorage.setItem('customerId', custId || '');
    setToken(tok);
    setCustomerId(custId);
  };

  const handleLogout = () => {
    localStorage.clear();
    setToken(null);
    setCustomerId(null);
  };

  useEffect(() => {
    if (token || !AUTO_LOGIN) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await listCustomers(0, 1);
        const first = Array.isArray(res.data) && res.data[0];
        if (!first) throw new Error('no seeded members yet');
        const r = await apiLogin(first.email, DEMO_PASSWORD);
        if (cancelled) return;
        handleLogin(r.data.access_token, r.data.customer_id || first.id);
      } catch (e) {
        if (!cancelled) setAutoLoginError(e.message || 'auto-login failed');
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  if (!token) {
    if (!AUTO_LOGIN || autoLoginError) return <Login onLogin={handleLogin} />;
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', color: '#888', fontSize: 14 }}>
        Signing in…
      </div>
    );
  }

  return (
    <BrowserRouter>
      <NavBar onLogout={handleLogout} />
      <div style={{ padding: 24 }}>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" />} />
          <Route path="/dashboard" element={<Dashboard customerId={customerId} />} />
          <Route path="/accounts" element={<Accounts customerId={customerId} />} />
          <Route path="/transactions" element={<Transactions customerId={customerId} />} />
          <Route path="/fraud" element={<FraudAlerts />} />
          <Route path="/chaos" element={<ChaosPanel customerId={customerId} />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
